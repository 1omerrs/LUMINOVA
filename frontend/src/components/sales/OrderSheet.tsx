import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { fetchRecords, statusLabel, statusTone, type FinanceRecord } from "../../lib/finance.ts";
import { ApiRequestError } from "../../lib/http.ts";
import { createLink } from "../../lib/intent.ts";
import { useWorkspace } from "../../lib/workspace.ts";
import { RecordEditor } from "../finance/RecordEditor.tsx";
import { formatQuantity } from "../../lib/inventory.ts";
import { timeAgo } from "../../lib/notifications.ts";
import {
  fetchOrder,
  formatDate,
  formatMoney,
  percentText,
  statusLabels,
  statusTone as orderTone,
  transitionOrder,
  type OrderAction,
  type OrderDetail,
  type StockCheck,
} from "../../lib/sales.ts";
import { Alert, Button, Spinner, TextArea } from "../forms/Controls.tsx";
import { Sheet } from "../ui/Sheet.tsx";

function StockWarning({ checks, status }: { checks: StockCheck[]; status: OrderDetail["status"] }) {
  const short = checks.filter((check) => Number(check.short) > 0);
  if (short.length === 0) return null;
  const blocked = short.some((check) => Number(check.on_hand) < Number(check.needed));
  const title = status === "draft" ? "Onaylarsanız stok yetmeyecek" : blocked ? "Teslim için stok yetmiyor" : "Teslim, başka siparişlere ayrılan stoğu kullanır";
  const hint = blocked
    ? "Stok girişi yapın veya üretim emri açın; stok yetene kadar teslim yapılamaz."
    : "Şimdi teslim ederseniz daha önce onaylanan siparişler eksik kalır. Stok girişi veya üretim emriyle açığı kapatın.";
  return (
    <section aria-labelledby="stock-warning-title" className="rounded-xl bg-warning/[0.08] px-4 py-3.5 ring-1 ring-inset ring-warning/25">
      <h3 id="stock-warning-title" className="text-[13.5px] font-semibold text-warning-text">
        {title}
      </h3>
      <ul className="mt-2 space-y-1.5 text-[13px] leading-5 text-graphite">
        {short.map((check) => (
          <li key={check.product_id}>
            <span className="font-semibold">{check.name}:</span> {formatQuantity(check.short)} {check.unit} eksik. Gereken {formatQuantity(check.needed)}, stokta{" "}
            {formatQuantity(check.on_hand)}
            {Number(check.reserved_elsewhere) > 0 ? `, bunun ${formatQuantity(check.reserved_elsewhere)} kadarı başka siparişlere veya üretime ayrılmış` : ""}.
            {Number(check.incoming) > 0 ? ` Üretimde ${formatQuantity(check.incoming)} ${check.unit} var.` : ""}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[12.5px] text-slate">{hint}</p>
    </section>
  );
}

const actionCopy: Record<OrderAction, { label: string; pending: string; confirm: string; explain: (order: OrderDetail) => string }> = {
  confirm: {
    label: "Siparişi onayla",
    pending: "Onaylanıyor",
    confirm: "Onayla",
    explain: () => "Onaylanan sipariş artık düzenlenemez. Stok teslimde düşülür; o zamana kadar ürünler bu sipariş için ayrılmış görünür.",
  },
  fulfil: {
    label: "Teslim et",
    pending: "Stok düşülüyor",
    confirm: "Teslim edildi olarak işaretle",
    explain: () => "Ürün satırlarının miktarı stoktan aynı anda düşülür. Stok yetmezse işlem yapılmaz.",
  },
  cancel: {
    label: "İptal et",
    pending: "İptal ediliyor",
    confirm: "Siparişi iptal et",
    explain: (order) => (order.stock_posted ? "Teslim edilen ürünler stoğa geri girer. Bu işlem geri alınamaz." : "Sipariş iptal edilir. Bu işlem geri alınamaz."),
  },
};

export function OrderSheet({
  orderId,
  onClose,
  onEdit,
  onChanged,
}: {
  orderId: string;
  onClose: () => void;
  onEdit: (order: OrderDetail) => void;
  onChanged: (order: OrderDetail) => void;
}) {
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [loadError, setLoadError] = useState("");
  const [action, setAction] = useState<OrderAction | null>(null);
  const [note, setNote] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const confirmRef = useRef<HTMLElement>(null);
  const statusRef = useRef<HTMLDivElement>(null);
  const { modules } = useWorkspace();
  const financeOn = modules.some((item) => item.key === "finance" && item.enabled);
  const customersOn = modules.some((item) => item.key === "customers" && item.enabled);
  const projectsOn = modules.some((item) => item.key === "projects" && item.enabled);
  const [income, setIncome] = useState<FinanceRecord | null | undefined>(undefined);
  const [incomeReload, setIncomeReload] = useState(0);
  const [creatingIncome, setCreatingIncome] = useState<string | null>(null);

  useEffect(() => {
    if (action) confirmRef.current?.querySelector("textarea")?.focus();
  }, [action]);

  useEffect(() => {
    if (!financeOn) return;
    let cancelled = false;
    fetchRecords({ orderId, kind: "income", pageSize: 10 })
      .then((page) => {
        if (!cancelled) setIncome(page.items.find((item) => item.status !== "cancelled") ?? null);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [financeOn, orderId, incomeReload]);

  useEffect(() => {
    let cancelled = false;
    fetchOrder(orderId)
      .then((next) => {
        if (!cancelled) setOrder(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setLoadError(caught instanceof ApiRequestError ? caught.message : "Sipariş yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [orderId]);

  async function run() {
    if (!order || !action) return;
    setPending(true);
    setError("");
    try {
      const next = await transitionOrder(order.id, action, note);
      setOrder(next);
      setIncomeReload((value) => value + 1);
      onChanged(next);
      setAction(null);
      setNote("");
      requestAnimationFrame(() => statusRef.current?.focus());
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "İşlem tamamlanamadı.");
    } finally {
      setPending(false);
    }
  }

  const available: OrderAction[] = !order
    ? []
    : order.status === "draft"
      ? ["confirm", "cancel"]
      : order.status === "confirmed"
        ? ["fulfil", "cancel"]
        : order.status === "fulfilled"
          ? ["cancel"]
          : [];

  return (
    <Sheet
      wide
      title={order ? order.code : "Sipariş"}
      description={order ? `${order.customer_name} · ${formatDate(order.order_date)}` : undefined}
      busy={pending}
      onClose={onClose}
      footer={
        order && available.length > 0 && !action ? (
          <>
            {order.status === "draft" ? (
              <Button variant="quiet" onClick={() => onEdit(order)}>
                Düzenle
              </Button>
            ) : null}
            {available.map((item) => (
              <Button key={item} variant={item === "cancel" ? "quiet" : "primary"} onClick={() => setAction(item)} className={item === "cancel" ? "text-error-text" : ""}>
                {actionCopy[item].label}
              </Button>
            ))}
          </>
        ) : undefined
      }
    >
      {loadError ? (
        <Alert tone="error">{loadError}</Alert>
      ) : !order ? (
        <p role="status" className="flex items-center gap-2.5 text-[14px] text-slate">
          <Spinner className="h-4 w-4 text-violet" /> Sipariş yükleniyor.
        </p>
      ) : (
        <div className="space-y-6">
          <div ref={statusRef} tabIndex={-1} className="flex flex-wrap items-center justify-between gap-3 rounded-lg outline-none">
            <span className={`rounded-full px-2.5 py-1 text-[12px] font-semibold ${orderTone[order.status]}`}>{statusLabels[order.status]}</span>
            <p className="text-[13px] text-slate">
              {order.stock_posted ? (order.status === "cancelled" ? "Stok iade edildi" : "Stoktan düşüldü") : "Stok henüz düşülmedi"}
            </p>
          </div>
          {projectsOn && order.status !== "cancelled" ? (
            <Link
              to={createLink("/panel/projeler", { id: order.customer_id, label: order.customer_name }, { kind: "order", id: order.id, label: order.code })}
              className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-violet hover:underline"
            >
              Bu siparişten proje başlat
            </Link>
          ) : null}
          {order.source_quote_code ? (
            <p className="text-[13px] text-slate">
              Kaynak teklif:{" "}
              <Link to="/panel/musteriler?bolum=teklifler" className="font-mono font-semibold text-ink-soft hover:text-violet">
                {order.source_quote_code}
              </Link>
            </p>
          ) : null}

          {order.automation.length > 0 ? (
            <Alert tone="success">
              <span className="font-semibold">Satış kuralları çalıştı.</span> {order.automation.join(" ")}
            </Alert>
          ) : null}

          <StockWarning checks={order.stock_check} status={order.status} />

          {action ? (
            <section ref={confirmRef} className="space-y-3 rounded-2xl border border-violet/25 bg-violet/[0.03] p-4" aria-live="polite">
              <p className="text-[14px] font-semibold">{actionCopy[action].confirm}</p>
              <p className="text-[13px] leading-5 text-slate">{actionCopy[action].explain(order)}</p>
              <TextArea label="Not (isteğe bağlı)" name="transition-note" rows={2} maxLength={300} value={note} onValue={setNote} />
              {error ? <Alert tone="error">{error}</Alert> : null}
              <div className="flex justify-end gap-2">
                <Button
                  variant="quiet"
                  disabled={pending}
                  onClick={() => {
                    setAction(null);
                    setError("");
                    statusRef.current?.focus();
                  }}
                >
                  Vazgeç
                </Button>
                <Button variant={action === "cancel" ? "danger" : "primary"} pending={pending} pendingLabel={actionCopy[action].pending} onClick={() => void run()}>
                  {actionCopy[action].confirm}
                </Button>
              </div>
            </section>
          ) : null}

          <div className="overflow-hidden rounded-2xl border border-mist/80">
            <table className="w-full text-left text-[14px]">
              <thead className="bg-cloud/60 text-[12px] text-slate">
                <tr>
                  <th scope="col" className="px-4 py-2 font-medium">Ürün / açıklama</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">Miktar</th>
                  <th scope="col" className="hidden px-3 py-2 text-right font-medium sm:table-cell">Birim fiyat</th>
                  <th scope="col" className="hidden px-3 py-2 text-right font-medium sm:table-cell">KDV</th>
                  <th scope="col" className="px-4 py-2 text-right font-medium">Tutar</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-mist/60">
                {order.items.map((item) => (
                  <tr key={item.id}>
                    <td className="px-4 py-2.5">
                      <p className="font-medium">{item.description}</p>
                      {item.product_sku ? <p className="font-mono text-[12px] text-slate">{item.product_sku}</p> : <p className="text-[12px] text-slate">Stok dışı satır</p>}
                      {item.discount_rate && item.discount_rate !== "0" ? (
                        <p className="text-[12px] text-success-text">
                          {percentText(item.discount_rate)} iskonto · −{formatMoney(item.line_discount, order.currency)}
                        </p>
                      ) : null}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums">
                      {formatQuantity(item.quantity)} {item.product_unit ?? ""}
                    </td>
                    <td className="hidden whitespace-nowrap px-3 py-2.5 text-right tabular-nums sm:table-cell">{formatMoney(item.unit_price, order.currency)}</td>
                    <td className="hidden px-3 py-2.5 text-right text-slate sm:table-cell">%{item.vat_rate}</td>
                    <td className="whitespace-nowrap px-4 py-2.5 text-right font-semibold tabular-nums">{formatMoney(item.line_total, order.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <dl className="space-y-1.5 border-t border-mist/70 bg-cloud/40 px-4 py-3 text-[14px]">
              {Number(order.discount_total) > 0 ? (
                <div className="flex justify-between">
                  <dt className="text-slate">İskonto</dt>
                  <dd className="tabular-nums text-success-text">−{formatMoney(order.discount_total, order.currency)}</dd>
                </div>
              ) : null}
              <div className="flex justify-between">
                <dt className="text-slate">Ara toplam</dt>
                <dd className="tabular-nums">{formatMoney(order.subtotal, order.currency)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate">KDV</dt>
                <dd className="tabular-nums">{formatMoney(order.vat_total, order.currency)}</dd>
              </div>
              <div className="flex justify-between text-[16px] font-semibold">
                <dt>Genel toplam</dt>
                <dd className="tabular-nums">{formatMoney(order.total, order.currency)}</dd>
              </div>
            </dl>
          </div>

          {financeOn && order.status !== "draft" && income !== undefined ? (
            <section aria-labelledby="income-title" className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-mist/80 px-4 py-3">
              <div className="min-w-0">
                <h3 id="income-title" className="text-[13px] font-semibold">
                  Gelir kaydı
                </h3>
                {income ? (
                  <p className="mt-1 flex flex-wrap items-center gap-2 text-[13px]">
                    <span className={`rounded-full px-2 py-0.5 text-[12px] font-semibold ${statusTone(income)}`}>{statusLabel(income)}</span>
                    <span className="font-semibold tabular-nums">{formatMoney(income.amount, income.currency)}</span>
                    {order.status === "cancelled" ? <span className="text-warning-text">Sipariş iptal edildi; gelir kaydını kontrol edin.</span> : null}
                  </p>
                ) : (
                  <p className="mt-0.5 text-[13px] text-slate">{order.status === "cancelled" ? "İptal edilen sipariş gelire işlenmez." : "Bu sipariş henüz gelire işlenmedi."}</p>
                )}
              </div>
              {income ? (
                <Link to="/panel/finans" className="text-[13px] font-semibold text-violet hover:underline">
                  Finansal Takip'te aç
                </Link>
              ) : order.status !== "cancelled" ? (
                <Button variant="quiet" onClick={() => setCreatingIncome(new Date().toLocaleDateString("sv-SE"))}>
                  Gelir kaydı oluştur
                </Button>
              ) : null}
            </section>
          ) : null}

          {order.note ? (
            <section>
              <h3 className="text-[13px] font-semibold text-slate">Not</h3>
              <p className="mt-1 whitespace-pre-line text-[14px] leading-6">{order.note}</p>
            </section>
          ) : null}

          <section aria-labelledby="timeline-title">
            <h3 id="timeline-title" className="text-[14px] font-semibold">
              Durum geçmişi
            </h3>
            <ol className="mt-3 space-y-4 border-l border-mist pl-5">
              {[...order.events].reverse().map((event, index) => (
                <li key={`${event.created_at}-${index}`} className="relative">
                  <span aria-hidden className="absolute -left-[26px] top-1 h-3 w-3 rounded-full border-2 border-white bg-violet ring-1 ring-violet/30" />
                  <p className="text-[14px] font-medium">{statusLabels[event.to_status]}</p>
                  {event.note ? <p className="mt-0.5 text-[13px] text-slate">{event.note}</p> : null}
                  <p className="mt-0.5 text-[12px] text-slate/80">
                    {event.actor ?? "Sistem"} · <time dateTime={event.created_at}>{timeAgo(event.created_at)}</time>
                  </p>
                </li>
              ))}
            </ol>
          </section>
        </div>
      )}
      {creatingIncome && order ? (
        <RecordEditor
          record={null}
          prefill={{
            kind: "income",
            category: "Satış",
            description: `${order.code} siparişi`,
            amount: order.total,
            currency: order.currency,
            customer_id: order.customer_id,
            customerName: order.customer_name,
            order_id: order.id,
            orderCode: order.code,
            record_date: order.order_date,
          }}
          customersOn={customersOn}
          today={creatingIncome}
          onClose={() => setCreatingIncome(null)}
          onSaved={() => {
            setCreatingIncome(null);
            setIncomeReload((value) => value + 1);
          }}
        />
      ) : null}
    </Sheet>
  );
}
