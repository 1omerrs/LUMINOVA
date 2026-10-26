import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { ApiRequestError } from "../../lib/http.ts";
import { formatQuantity, unitShort, type Unit } from "../../lib/inventory.ts";
import { timeAgo } from "../../lib/notifications.ts";
import {
  cancelProductionOrder,
  completeProductionOrder,
  fetchProductionOrder,
  productionStatusLabels,
  productionStatusTone,
  startProductionOrder,
  type ProductionDetail,
} from "../../lib/production.ts";
import { formatDay } from "../../lib/tasks.ts";
import { Alert, Button, Spinner, TextArea } from "../forms/Controls.tsx";
import { Icon } from "../ui/Icon.tsx";
import { Sheet } from "../ui/Sheet.tsx";

type Action = "complete" | "cancel";

export function ProductionSheet({
  orderId,
  onClose,
  onEdit,
  onChanged,
}: {
  orderId: string;
  onClose: () => void;
  onEdit: (order: ProductionDetail) => void;
  onChanged: (order: ProductionDetail) => void;
}) {
  const [order, setOrder] = useState<ProductionDetail | null>(null);
  const [loadError, setLoadError] = useState("");
  const [action, setAction] = useState<Action | null>(null);
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const panel = useRef<HTMLElement>(null);
  const statusRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetchProductionOrder(orderId)
      .then((next) => {
        if (!cancelled) setOrder(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setLoadError(caught instanceof ApiRequestError ? caught.message : "İş emri yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [orderId]);

  useEffect(() => {
    if (!action) return;
    const target = panel.current?.querySelector<HTMLElement>(action === "cancel" ? "textarea" : "button[data-confirm]");
    target?.focus();
  }, [action]);

  async function run(task: () => Promise<ProductionDetail>) {
    setPending(true);
    setError("");
    try {
      const next = await task();
      setOrder(next);
      setAction(null);
      setReason("");
      onChanged(next);
      requestAnimationFrame(() => statusRef.current?.focus());
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "İşlem tamamlanamadı.");
    } finally {
      setPending(false);
    }
  }

  const open = order ? order.status === "planned" || order.status === "in_progress" : false;
  const unit = (order?.unit ?? "adet") as Unit;

  return (
    <Sheet
      wide
      title={order ? order.code : "İş emri"}
      description={order ? `${formatQuantity(order.quantity)} ${unitShort(unit)} ${order.product_name}` : undefined}
      busy={pending}
      onClose={onClose}
      footer={
        order && open && !action ? (
          <>
            <Button variant="quiet" className="mr-auto text-error-text" onClick={() => setAction("cancel")}>
              İptal et
            </Button>
            {order.status === "planned" ? (
              <>
                <Button variant="quiet" onClick={() => onEdit(order)}>
                  Düzenle
                </Button>
                <Button variant="quiet" pending={pending} pendingLabel="Başlatılıyor" onClick={() => void run(() => startProductionOrder(order.id))}>
                  Üretime başla
                </Button>
              </>
            ) : null}
            <Button onClick={() => setAction("complete")}>Tamamla</Button>
          </>
        ) : undefined
      }
    >
      {loadError ? (
        <Alert tone="error">{loadError}</Alert>
      ) : !order ? (
        <p role="status" className="flex items-center gap-2.5 text-[14px] text-slate">
          <Spinner className="h-4 w-4 text-violet" /> İş emri yükleniyor.
        </p>
      ) : (
        <div className="space-y-6">
          <div ref={statusRef} tabIndex={-1} className="flex flex-wrap items-center justify-between gap-3 rounded-lg outline-none">
            <span className={`rounded-full px-2.5 py-1 text-[12px] font-semibold ${productionStatusTone[order.status]}`}>{productionStatusLabels[order.status]}</span>
            <p className="text-[13px] text-slate">
              {order.stock_posted ? "Stok hareketleri yazıldı" : order.status === "cancelled" ? "Stoğa dokunulmadı" : order.shortage ? <span className="font-medium text-error-text">Malzeme eksik</span> : "Malzemeler yeterli"}
            </p>
          </div>

          {action ? (
            <section ref={panel} aria-live="polite" className={`space-y-3 rounded-2xl border p-4 ${action === "cancel" ? "border-error/25 bg-error/[0.03]" : "border-violet/25 bg-violet/[0.03]"}`}>
              <p className="text-[14px] font-semibold">{action === "cancel" ? "İş emrini iptal et" : "Üretimi tamamla"}</p>
              <p className="text-[13px] leading-5 text-slate">
                {action === "cancel"
                  ? "Stoğa dokunulmaz. İptal nedeni kayda yazılır ve iş emri yeniden açılamaz."
                  : `Aşağıdaki malzemeler stoktan düşülür ve ${formatQuantity(order.quantity)} ${unitShort(unit)} ${order.product_name} stoğa girer. Bir malzeme yetmezse hiçbir hareket yazılmaz.`}
              </p>
              {action === "cancel" ? <TextArea label="İptal nedeni" name="reason" rows={2} maxLength={300} value={reason} onValue={setReason} /> : null}
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
                {action === "cancel" ? (
                  <Button
                    variant="danger"
                    pending={pending}
                    pendingLabel="İptal ediliyor"
                    onClick={() => {
                      if (reason.trim().length < 3) {
                        setError("İptal nedenini en az 3 karakterle yazın.");
                        return;
                      }
                      void run(() => cancelProductionOrder(order.id, reason));
                    }}
                  >
                    İş emrini iptal et
                  </Button>
                ) : (
                  <Button data-confirm pending={pending} pendingLabel="Stok işleniyor" onClick={() => void run(() => completeProductionOrder(order.id))}>
                    Tamamla ve stoğa işle
                  </Button>
                )}
              </div>
            </section>
          ) : error ? (
            <Alert tone="error">{error}</Alert>
          ) : null}

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Fact label="Üretilecek" value={`${formatQuantity(order.quantity)} ${unitShort(unit)}`} note={order.product_sku} />
            <Fact label="Mevcut ürün stoğu" value={`${formatQuantity(order.product_stock)} ${unitShort(unit)}`} />
            <Fact label="Plan tarihi" value={order.planned_date ? formatDay(order.planned_date) : "Belirtilmedi"} />
          </div>
          {order.sales_order_code || order.project_name ? (
            <p className="text-[13px] text-slate">
              {order.sales_order_code ? (
                <>
                  Bağlı sipariş:{" "}
                  <Link to="/panel/satis" className="font-mono font-semibold text-ink-soft hover:text-violet">
                    {order.sales_order_code}
                  </Link>
                </>
              ) : null}
              {order.sales_order_code && order.project_name ? " · " : null}
              {order.project_name ? (
                <>
                  Proje:{" "}
                  <Link to="/panel/projeler" className="font-semibold text-ink-soft hover:text-violet">
                    {order.project_name}
                  </Link>
                </>
              ) : null}
            </p>
          ) : null}

          <section aria-labelledby="materials-title" className="overflow-hidden rounded-2xl border border-mist/80">
            <h3 id="materials-title" className="border-b border-mist/70 bg-cloud/60 px-4 py-2.5 text-[13px] font-semibold">
              Malzemeler
            </h3>
            <table className="w-full text-left text-[14px]">
              <thead className="text-[12px] text-slate">
                <tr>
                  <th scope="col" className="px-4 py-2 font-medium">Malzeme</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">Gereken</th>
                  <th scope="col" className="px-4 py-2 text-right font-medium">{order.stock_posted ? "Kalan stok" : "Stokta"}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-mist/60">
                {order.materials.map((line) => (
                  <tr key={line.product_id}>
                    <td className="px-4 py-2.5">
                      <p className="font-medium">{line.name}</p>
                      <p className="font-mono text-[12px] text-slate">{line.sku}</p>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-right tabular-nums">
                      {formatQuantity(line.quantity)} {unitShort(line.unit as Unit)}
                    </td>
                    <td className={`whitespace-nowrap px-4 py-2.5 text-right tabular-nums ${line.short ? "font-semibold text-error-text" : "text-slate"}`}>
                      <span className="inline-flex items-center gap-1.5">
                        {line.short ? <Icon name="alert" className="h-3.5 w-3.5" /> : null}
                        {formatQuantity(line.available)} {unitShort(line.unit as Unit)}
                      </span>
                      {line.short ? <span className="sr-only"> (yetersiz)</span> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          {order.note ? <p className="whitespace-pre-line text-[14px] leading-6">{order.note}</p> : null}
          {order.cancel_reason ? <Alert tone="info">İptal nedeni: {order.cancel_reason}</Alert> : null}

          <section aria-labelledby="production-history">
            <h3 id="production-history" className="text-[14px] font-semibold">
              Geçmiş
            </h3>
            <ol className="mt-3 space-y-3 border-l border-mist pl-5 text-[14px]">
              {[
                order.cancelled_at ? { label: "İptal edildi", at: order.cancelled_at } : null,
                order.completed_at ? { label: "Tamamlandı, stok işlendi", at: order.completed_at } : null,
                order.started_at ? { label: "Üretime başlandı", at: order.started_at } : null,
                { label: `Oluşturuldu${order.created_by ? ` · ${order.created_by}` : ""}`, at: order.created_at },
              ]
                .filter((item): item is { label: string; at: string } => item !== null)
                .map((item) => (
                  <li key={item.label} className="relative">
                    <span aria-hidden className="absolute -left-[26px] top-1 h-3 w-3 rounded-full border-2 border-white bg-violet ring-1 ring-violet/30" />
                    <p className="font-medium">{item.label}</p>
                    <time dateTime={item.at} className="text-[12px] text-slate/80">
                      {timeAgo(item.at)}
                    </time>
                  </li>
                ))}
            </ol>
          </section>
        </div>
      )}
    </Sheet>
  );
}

function Fact({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-xl border border-mist/80 px-4 py-3">
      <p className="text-[12px] text-slate">{label}</p>
      <p className="mt-0.5 text-[15px] font-semibold tabular-nums">{value}</p>
      {note ? <p className="font-mono text-[12px] text-slate">{note}</p> : null}
    </div>
  );
}
