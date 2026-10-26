import { useEffect, useRef, useState } from "react";
import {
  addPayment,
  cancelRecord,
  fetchRecord,
  fieldLabels,
  kindLabels,
  methodLabels,
  payloadFrom,
  removePayment,
  statusLabel,
  statusTone,
  updateRecord,
  type FinanceRecord,
  type PaymentMethod,
  type RecordDetail,
  type Revision,
} from "../../lib/finance.ts";
import { ApiRequestError } from "../../lib/http.ts";
import { timeAgo } from "../../lib/notifications.ts";
import { formatMoney, parseMoney, type Currency } from "../../lib/sales.ts";
import { formatDay } from "../../lib/tasks.ts";
import { Alert, Button, Spinner, TextArea } from "../forms/Controls.tsx";
import { Icon } from "../ui/Icon.tsx";
import { Sheet } from "../ui/Sheet.tsx";

const valueStatus: Record<string, string> = { pending: "Bekliyor", paid: "Ödendi", cancelled: "İptal edildi", income: "Gelir", expense: "Gider" };

function describe(field: string, value: string | null, currency: Currency, kind: FinanceRecord["kind"]): string {
  if (value === null || value === "") return "boş";
  if (field === "amount" || field === "paid_amount") return formatMoney(value, currency);
  if (field === "status" && value === "partial") return kind === "income" ? "Kısmen tahsil edildi" : "Kısmen ödendi";
  if (field === "status" && value === "paid" && kind === "income") return "Tahsil edildi";
  if (field === "status" || field === "kind") return valueStatus[value] ?? value;
  if (field.endsWith("_date") || field === "paid_on") return formatDay(value);
  if (field === "customer_id") return "değişti";
  return value;
}

export function RecordSheet({
  recordId,
  today,
  onClose,
  onEdit,
  onChanged,
}: {
  recordId: string;
  today: string;
  onClose: () => void;
  onEdit: (record: FinanceRecord) => void;
  onChanged: (record: RecordDetail, message: string) => void;
}) {
  const [record, setRecord] = useState<RecordDetail | null>(null);
  const [loadError, setLoadError] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [payment, setPayment] = useState<{ amount: string; paid_on: string; method: PaymentMethod; note: string } | null>(null);
  const panel = useRef<HTMLElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetchRecord(recordId)
      .then((found) => {
        if (!cancelled) setRecord(found);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setLoadError(caught instanceof ApiRequestError ? caught.message : "Kayıt yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [recordId]);

  useEffect(() => {
    if (cancelling) panel.current?.querySelector("textarea")?.focus();
  }, [cancelling]);

  function startPayment() {
    if (!record) return;
    setPayment({ amount: record.remaining.replace(".", ","), paid_on: today, method: "transfer", note: "" });
    setError("");
  }

  async function savePayment() {
    if (!record || !payment) return;
    const amount = parseMoney(payment.amount);
    if (amount === null || Number(amount) <= 0) return setError("Geçerli bir tutar girin.");
    if (Number(amount) > Number(record.remaining)) return setError(`Kalan tutar ${formatMoney(record.remaining, record.currency)}; daha fazlası girilemez.`);
    setPending(true);
    setError("");
    try {
      const next = await addPayment(record.id, { ...payment, amount });
      setRecord(next);
      setPayment(null);
      onChanged(next, next.status === "paid" ? `“${next.description}” ${statusLabel(next).toLocaleLowerCase("tr")}.` : `${formatMoney(amount, next.currency)} kaydedildi; kalan ${formatMoney(next.remaining, next.currency)}.`);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Ödeme kaydedilemedi.");
    } finally {
      setPending(false);
    }
  }

  async function dropPayment(paymentId: string) {
    if (!record) return;
    setPending(true);
    setError("");
    try {
      const next = await removePayment(record.id, paymentId);
      setRecord(next);
      onChanged(next, "Ödeme geri alındı.");
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Ödeme geri alınamadı.");
    } finally {
      setPending(false);
    }
  }

  async function payInFull() {
    if (!record) return;
    setPending(true);
    setError("");
    try {
      const next = await updateRecord(record.id, payloadFrom(record, { status: "paid", paid_on: today }));
      setRecord(next);
      onChanged(next, `“${next.description}” ${statusLabel(next).toLocaleLowerCase("tr")}.`);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Kayıt güncellenemedi.");
    } finally {
      setPending(false);
    }
  }

  async function confirmCancel() {
    if (!record) return;
    if (reason.trim().length < 3) {
      setError("İptal nedenini en az 3 karakterle yazın.");
      return;
    }
    setPending(true);
    setError("");
    try {
      const next = await cancelRecord(record.id, reason);
      setRecord(next);
      setCancelling(false);
      setReason("");
      onChanged(next, `“${next.description}” iptal edildi.`);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Kayıt iptal edilemedi.");
    } finally {
      setPending(false);
    }
  }

  const income = record?.kind === "income";
  const party = record?.customer_name ?? record?.counterparty ?? null;

  return (
    <Sheet
      title={record?.description ?? "Kayıt"}
      description={record ? `${kindLabels[record.kind]} · ${record.category}` : undefined}
      busy={pending}
      onClose={onClose}
      footer={
        record && record.status !== "cancelled" && !cancelling && !payment ? (
          <>
            <Button variant="quiet" className="mr-auto text-error-text" onClick={() => setCancelling(true)} disabled={pending}>
              İptal et
            </Button>
            <Button variant="quiet" onClick={() => onEdit(record)} disabled={pending}>
              Düzenle
            </Button>
            {record.status === "pending" || record.status === "partial" ? (
              <>
                <Button variant="quiet" onClick={startPayment} disabled={pending}>
                  {income ? "Kısmi tahsilat" : "Kısmi ödeme"}
                </Button>
                <Button onClick={() => void payInFull()} pending={pending} pendingLabel="Kaydediliyor">
                  {record.status === "partial" ? "Kalanı" : "Tamamını"} {income ? "tahsil et" : "öde"}
                </Button>
              </>
            ) : null}
          </>
        ) : undefined
      }
    >
      {loadError ? (
        <Alert tone="error">{loadError}</Alert>
      ) : !record ? (
        <p role="status" className="flex items-center gap-2.5 text-[14px] text-slate">
          <Spinner className="h-4 w-4 text-violet" /> Kayıt yükleniyor.
        </p>
      ) : (
        <div className="space-y-6">
          <div>
            <p className={`font-display text-[34px] font-semibold leading-none tracking-tight tabular-nums ${record.status === "cancelled" ? "text-slate line-through decoration-slate/40" : income ? "text-success-text" : "text-graphite"}`}>
              {income ? "+" : "−"}
              {formatMoney(record.amount, record.currency)}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className={`rounded-full px-2.5 py-1 text-[12px] font-semibold ${statusTone(record)}`}>{statusLabel(record)}</span>
              {record.overdue ? <span className="text-[13px] font-medium text-error-text">Vadesi geçti</span> : null}
            </div>
            {Number(record.paid_amount) > 0 && record.status !== "paid" ? (
              <div className="mt-4">
                <div className="flex justify-between text-[13px]">
                  <span className="text-slate">
                    {income ? "Tahsil edilen" : "Ödenen"} <span className="font-semibold text-graphite tabular-nums">{formatMoney(record.paid_amount, record.currency)}</span>
                  </span>
                  {record.status === "partial" ? (
                    <span className="text-slate">
                      Kalan <span className="font-semibold text-graphite tabular-nums">{formatMoney(record.remaining, record.currency)}</span>
                    </span>
                  ) : null}
                </div>
                <div aria-hidden className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-mist/70">
                  <div className="h-full rounded-full bg-violet" style={{ width: `${Math.min((Number(record.paid_amount) / Number(record.amount)) * 100, 100)}%` }} />
                </div>
              </div>
            ) : null}
          </div>

          {payment ? (
            <section className="space-y-3 rounded-2xl border border-violet/25 bg-violet-wash/60 p-4" aria-live="polite">
              <p className="text-[14px] font-semibold">{income ? "Tahsilat kaydet" : "Ödeme kaydet"}</p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <label className="block text-[12px] font-medium text-graphite">
                  Tutar ({record.currency})
                  <input
                    inputMode="decimal"
                    value={payment.amount}
                    onChange={(event) => setPayment({ ...payment, amount: event.target.value })}
                    className="mt-1 h-10 w-full rounded-lg border border-mist bg-surface px-3 text-right text-[14px] tabular-nums outline-none focus:border-violet"
                  />
                </label>
                <label className="block text-[12px] font-medium text-graphite">
                  Tarih
                  <input
                    type="date"
                    max={today}
                    value={payment.paid_on}
                    onChange={(event) => setPayment({ ...payment, paid_on: event.target.value })}
                    className="mt-1 h-10 w-full rounded-lg border border-mist bg-surface px-3 text-[14px] outline-none focus:border-violet"
                  />
                </label>
                <label className="col-span-2 block text-[12px] font-medium text-graphite sm:col-span-1">
                  Yöntem
                  <select
                    value={payment.method}
                    onChange={(event) => setPayment({ ...payment, method: event.target.value as PaymentMethod })}
                    className="mt-1 h-10 w-full rounded-lg border border-mist bg-surface px-3 text-[14px] outline-none focus:border-violet"
                  >
                    {(Object.keys(methodLabels) as PaymentMethod[]).map((method) => (
                      <option key={method} value={method}>
                        {methodLabels[method]}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label className="block text-[12px] font-medium text-graphite">
                Not (isteğe bağlı)
                <input
                  value={payment.note}
                  maxLength={300}
                  onChange={(event) => setPayment({ ...payment, note: event.target.value })}
                  placeholder="Ör. dekont numarası"
                  className="mt-1 h-10 w-full rounded-lg border border-mist bg-surface px-3 text-[14px] outline-none focus:border-violet"
                />
              </label>
              {error ? <Alert tone="error">{error}</Alert> : null}
              <div className="flex justify-end gap-2">
                <Button variant="quiet" disabled={pending} onClick={() => setPayment(null)}>
                  Vazgeç
                </Button>
                <Button pending={pending} pendingLabel="Kaydediliyor" onClick={() => void savePayment()}>
                  Kaydet
                </Button>
              </div>
            </section>
          ) : null}

          {cancelling ? (
            <section ref={panel} className="space-y-3 rounded-2xl border border-error/25 bg-error/[0.03] p-4" aria-live="polite">
              <p className="text-[14px] font-semibold">Kaydı iptal et</p>
              <p className="text-[13px] leading-5 text-slate">Kayıt silinmez; tutarı özetlerden çıkar ve iptal nedeni geçmişe yazılır. Bu işlem geri alınamaz.</p>
              <TextArea label="İptal nedeni" name="reason" rows={2} maxLength={300} value={reason} onValue={setReason} />
              {error ? <Alert tone="error">{error}</Alert> : null}
              <div className="flex justify-end gap-2">
                <Button
                  variant="quiet"
                  disabled={pending}
                  onClick={() => {
                    setCancelling(false);
                    setError("");
                  }}
                >
                  Vazgeç
                </Button>
                <Button variant="danger" pending={pending} pendingLabel="İptal ediliyor" onClick={() => void confirmCancel()}>
                  Kaydı iptal et
                </Button>
              </div>
            </section>
          ) : error && !payment ? (
            <Alert tone="error">{error}</Alert>
          ) : null}

          <dl className="grid grid-cols-1 gap-x-6 gap-y-4 rounded-2xl border border-mist/80 p-5 text-[14px] sm:grid-cols-2">
            <Fact label="Kayıt tarihi" value={formatDay(record.record_date)} />
            <Fact label="Vade" value={record.due_date ? formatDay(record.due_date) : "Yok"} tone={record.overdue ? "text-error-text font-medium" : undefined} />
            {record.paid_on ? <Fact label={income ? "Tahsilat tarihi" : "Ödeme tarihi"} value={formatDay(record.paid_on)} /> : null}
            <Fact label={record.customer_name ? "Müşteri" : income ? "Kimden" : "Kime"} value={party ?? "Belirtilmedi"} />
            {record.order_code ? <Fact label="Sipariş" value={record.order_code} mono /> : null}
            {record.cancel_reason ? <Fact label="İptal nedeni" value={record.cancel_reason} /> : null}
            {record.note ? <Fact label="Not" value={record.note} wide /> : null}
          </dl>

          {record.payments.length > 0 ? (
            <section aria-labelledby="payments-title">
              <h3 id="payments-title" className="text-[12px] font-semibold uppercase tracking-[0.08em] text-slate">
                {income ? "Tahsilatlar" : "Ödemeler"}
              </h3>
              <ul className="mt-2 divide-y divide-hairline border-y border-hairline">
                {record.payments.map((item) => (
                  <li key={item.id} className="flex items-center gap-3 py-2.5 text-[13.5px]">
                    <span className="w-24 shrink-0 tabular-nums text-slate">{formatDay(item.paid_on)}</span>
                    <span className="min-w-0 flex-1 truncate">
                      {methodLabels[item.method]}
                      {item.note ? <span className="text-slate"> · {item.note}</span> : null}
                    </span>
                    <span className="shrink-0 font-semibold tabular-nums">{formatMoney(item.amount, record.currency)}</span>
                    {record.status !== "cancelled" ? (
                      <button
                        type="button"
                        aria-label={`${formatDay(item.paid_on)} tarihli ödemeyi geri al`}
                        disabled={pending}
                        onClick={() => void dropPayment(item.id)}
                        className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-slate hover:bg-error/[0.06] hover:text-error-text disabled:opacity-40"
                      >
                        <Icon name="close" className="h-3.5 w-3.5" />
                      </button>
                    ) : null}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section aria-labelledby="history-title">
            <h3 id="history-title" className="text-[14px] font-semibold">
              Kayıt geçmişi
            </h3>
            <ol className="mt-3 space-y-4 border-l border-mist pl-5">
              {[...record.revisions].reverse().map((revision) => (
                <HistoryItem key={revision.revision} revision={revision} currency={record.currency} kind={record.kind} />
              ))}
            </ol>
          </section>
        </div>
      )}
    </Sheet>
  );
}

function Fact({ label, value, tone, mono = false, wide = false }: { label: string; value: string; tone?: string; mono?: boolean; wide?: boolean }) {
  return (
    <div className={wide ? "sm:col-span-2" : undefined}>
      <dt className="text-[12px] text-slate">{label}</dt>
      <dd className={`mt-0.5 whitespace-pre-line ${mono ? "font-mono text-[13px]" : ""} ${tone ?? ""}`}>{value}</dd>
    </div>
  );
}

function HistoryItem({ revision, currency, kind }: { revision: Revision; currency: Currency; kind: FinanceRecord["kind"] }) {
  const title = {
    created: "Kayıt oluşturuldu",
    cancelled: "İptal edildi",
    updated: "Güncellendi",
    payment_added: kind === "income" ? "Tahsilat eklendi" : "Ödeme eklendi",
    payment_removed: kind === "income" ? "Tahsilat geri alındı" : "Ödeme geri alındı",
  }[revision.action];
  const lines = Object.entries(revision.changes).filter(([field]) => !(revision.action === "cancelled" && field === "status"));
  return (
    <li className="relative">
      <span aria-hidden className={`absolute -left-[26px] top-1 h-3 w-3 rounded-full border-2 border-white ring-1 ${revision.action === "cancelled" ? "bg-error ring-error/30" : "bg-violet ring-violet/30"}`} />
      <p className="text-[14px] font-medium">{title}</p>
      {revision.reason ? <p className="mt-0.5 text-[13px] text-slate">Neden: {revision.reason}</p> : null}
      {lines.length > 0 ? (
        <ul className="mt-1 space-y-0.5 text-[13px] text-slate">
          {lines.map(([field, change]) => (
            <li key={field}>
              {fieldLabels[field] ?? field}: {describe(field, change.from, currency, kind)} → <span className="text-graphite">{describe(field, change.to, currency, kind)}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <p className="mt-0.5 text-[12px] text-slate/80">
        {revision.actor ?? "Sistem"} · <time dateTime={revision.created_at}>{timeAgo(revision.created_at)}</time>
      </p>
    </li>
  );
}
