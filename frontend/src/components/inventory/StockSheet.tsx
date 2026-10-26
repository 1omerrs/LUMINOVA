import { useEffect, useState, type FormEvent } from "react";
import { ApiRequestError } from "../../lib/http.ts";
import {
  fetchMovements,
  formatQuantity,
  parseQuantity,
  recordMovement,
  unitShort,
  wholeUnitMessage,
  wholeUnits,
  type Movement,
  type MovementKind,
  type Product,
} from "../../lib/inventory.ts";
import { timeAgo } from "../../lib/notifications.ts";
import { Alert, Button, Field, Spinner, TextArea } from "../forms/Controls.tsx";
import { Icon } from "../ui/Icon.tsx";
import { Sheet } from "../ui/Sheet.tsx";

const kinds: { value: MovementKind; label: string; field: string; submit: string }[] = [
  { value: "in", label: "Giriş", field: "Eklenecek miktar", submit: "Girişi kaydet" },
  { value: "out", label: "Çıkış", field: "Çıkacak miktar", submit: "Çıkışı kaydet" },
  { value: "adjustment", label: "Sayım", field: "Sayılan miktar", submit: "Sayımı kaydet" },
];

const kindLabel: Record<MovementKind, string> = { in: "Giriş", out: "Çıkış", adjustment: "Sayım düzeltmesi" };

function newKey(): string {
  return `move-${crypto.randomUUID()}`;
}

export function StockSheet({ product, onClose, onChanged }: { product: Product; onClose: () => void; onChanged: (product: Product) => void }) {
  const [current, setCurrent] = useState(product);
  const [kind, setKind] = useState<MovementKind>("in");
  const [quantity, setQuantity] = useState("");
  const [note, setNote] = useState("");
  const [key, setKey] = useState(newKey);
  const [error, setError] = useState("");
  const [formError, setFormError] = useState("");
  const [saved, setSaved] = useState("");
  const [pending, setPending] = useState(false);
  const [history, setHistory] = useState<{ items: Movement[]; total: number; page: number } | null>(null);
  const [historyError, setHistoryError] = useState("");
  const [historyVersion, setHistoryVersion] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);

  const unit = unitShort(current.unit);
  const parsed = parseQuantity(quantity);
  const stock = Number(current.stock_quantity);
  const preview = parsed === null ? null : kind === "in" ? stock + Number(parsed) : kind === "out" ? stock - Number(parsed) : Number(parsed);
  const active = kinds.find((item) => item.value === kind) ?? kinds[0];

  useEffect(() => {
    let cancelled = false;
    fetchMovements(product.id, 1)
      .then((page) => {
        if (!cancelled) setHistory({ items: page.items, total: page.total, page: 1 });
      })
      .catch(() => {
        if (!cancelled) setHistoryError("Hareket geçmişi yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [product.id, historyVersion]);

  async function loadMore() {
    if (!history) return;
    setLoadingMore(true);
    try {
      const next = await fetchMovements(product.id, history.page + 1);
      setHistory({ items: [...history.items, ...next.items], total: next.total, page: next.page });
    } catch {
      setHistoryError("Hareket geçmişi yüklenemedi.");
    } finally {
      setLoadingMore(false);
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    setSaved("");
    if (parsed === null) {
      setError("Geçerli bir miktar girin. Örnek: 12 veya 2,5");
      return;
    }
    if (wholeUnits.has(current.unit) && !Number.isInteger(Number(parsed))) {
      setError(wholeUnitMessage(current.unit));
      return;
    }
    if (kind !== "adjustment" && Number(parsed) <= 0) {
      setError("Miktar sıfırdan büyük olmalı.");
      return;
    }
    if (kind === "out" && preview !== null && preview < 0) {
      setError(`Stokta yeterli miktar yok. Mevcut stok: ${formatQuantity(stock)} ${unit}.`);
      return;
    }
    setPending(true);
    try {
      const result = await recordMovement(current.id, { kind, quantity: parsed, note, idempotency_key: key });
      setCurrent(result.product);
      onChanged(result.product);
      setQuantity("");
      setNote("");
      setKey(newKey());
      setSaved(`${kindLabel[kind]} kaydedildi. Yeni stok: ${formatQuantity(result.product.stock_quantity)} ${unit}.`);
      setHistoryVersion((value) => value + 1);
    } catch (caught) {
      if (caught instanceof ApiRequestError && (caught.status === 409 || caught.status === 422)) setError(caught.message);
      else setFormError(caught instanceof ApiRequestError ? caught.message : "Stok hareketi kaydedilemedi.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Sheet
      title="Stok hareketi"
      description={
        <>
          <span className="font-mono text-[12px]">{current.sku}</span> · {current.name}
        </>
      }
      busy={pending}
      onClose={onClose}
      onSubmit={(event) => void onSubmit(event)}
      initialFocus='[name="quantity"]'
      footer={
        <>
          <Button type="button" variant="quiet" onClick={onClose} disabled={pending}>
            Kapat
          </Button>
          <Button type="submit" pending={pending} pendingLabel="Kaydediliyor">
            {active.submit}
          </Button>
        </>
      }
    >
      <div className="space-y-6">
        <section className="flex items-end justify-between gap-4 rounded-2xl bg-cloud px-5 py-4">
          <div>
            <p className="text-[12px] font-medium text-slate">Mevcut stok</p>
            <p className="mt-1 font-display text-[30px] font-semibold leading-none tabular-nums">
              {formatQuantity(current.stock_quantity)} <span className="text-[15px] font-medium text-slate">{unit}</span>
            </p>
          </div>
          <div className="text-right">
            <p className="text-[12px] text-slate">Minimum {formatQuantity(current.min_stock)} {unit}</p>
            {current.critical_level !== null ? (
              <p className="text-[12px] text-slate">
                Kritik {formatQuantity(current.critical_level)} {unit}
              </p>
            ) : null}
            {current.critical ? (
              <span className="mt-1 inline-flex rounded-full bg-error/10 px-2 py-0.5 text-[11px] font-semibold text-error-text">Kritik seviye</span>
            ) : current.low ? (
              <span className="mt-1 inline-flex rounded-full bg-warning/10 px-2 py-0.5 text-[11px] font-semibold text-warning-text">Minimumun altında</span>
            ) : null}
          </div>
        </section>

        <div className="space-y-4">
          <div role="radiogroup" aria-label="Hareket türü" className="grid grid-cols-3 rounded-xl bg-cloud p-1">
            {kinds.map((item) => (
              <button
                key={item.value}
                type="button"
                role="radio"
                aria-checked={kind === item.value}
                onClick={() => {
                  setKind(item.value);
                  setError("");
                }}
                className={`h-9 rounded-[9px] text-[13px] font-semibold transition-colors ${
                  kind === item.value ? "bg-surface text-graphite shadow-[0_1px_3px_rgba(16,19,28,0.12)]" : "text-slate hover:text-graphite"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
          <Field
            label={active.field}
            name="quantity"
            inputMode="decimal"
            autoComplete="off"
            placeholder="0"
            value={quantity}
            error={error}
            hint={
              preview !== null && Number.isFinite(preview) ? (
                <span>
                  Yeni stok:{" "}
                  <span className={`font-semibold tabular-nums ${preview < 0 ? "text-error-text" : "text-graphite"}`}>
                    {formatQuantity(preview)} {unit}
                  </span>
                </span>
              ) : (
                `Birim: ${unit}${kind === "adjustment" ? " · Raftaki gerçek miktarı girin." : ""}`
              )
            }
            onValue={(value) => {
              setQuantity(value);
              setError("");
            }}
          />
          <TextArea label="Not" name="note" rows={2} maxLength={300} value={note} onValue={setNote} hint="Örnek: Tedarikçi teslimatı, iade, ay sonu sayımı." />
          {formError ? <Alert tone="error">{formError}</Alert> : null}
          {saved ? <Alert tone="success">{saved}</Alert> : null}
        </div>

        <section aria-labelledby="history-title">
          <h3 id="history-title" className="text-[14px] font-semibold">
            Hareket geçmişi
          </h3>
          {historyError ? (
            <p className="mt-3 text-[13px] text-error-text">{historyError}</p>
          ) : !history ? (
            <p role="status" className="mt-3 flex items-center gap-2 text-[13px] text-slate">
              <Spinner className="h-4 w-4 text-violet" /> Yükleniyor.
            </p>
          ) : history.items.length === 0 ? (
            <p className="mt-3 text-[13px] text-slate">Bu ürün için henüz hareket yok.</p>
          ) : (
            <>
              <ul className="mt-3 divide-y divide-mist/60">
                {history.items.map((item) => {
                  const delta = Number(item.quantity);
                  return (
                    <li key={item.id} className="flex items-start gap-3 py-3">
                      <span
                        className={`mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg text-[13px] font-bold ${
                          delta > 0 ? "bg-success/10 text-success-text" : "bg-warning/10 text-warning-text"
                        }`}
                        aria-hidden
                      >
                        {delta > 0 ? "+" : "−"}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-[13px]">
                          <span className="font-semibold">{kindLabel[item.kind]}</span>{" "}
                          <span className="tabular-nums">
                            {delta > 0 ? "+" : "−"}
                            {formatQuantity(Math.abs(delta))} {unit}
                          </span>
                        </p>
                        {item.note ? <p className="mt-0.5 text-[12px] text-slate">{item.note}</p> : null}
                        <p className="mt-0.5 text-[12px] text-slate/80">
                          {item.actor ?? "Sistem"} · <time dateTime={item.created_at}>{timeAgo(item.created_at)}</time>
                        </p>
                      </div>
                      <p className="shrink-0 text-right text-[12px] text-slate">
                        Bakiye
                        <span className="block text-[13px] font-semibold tabular-nums text-graphite">
                          {formatQuantity(item.balance_after)} {unit}
                        </span>
                      </p>
                    </li>
                  );
                })}
              </ul>
              {history.items.length < history.total ? (
                <button
                  type="button"
                  onClick={() => void loadMore()}
                  disabled={loadingMore}
                  className="mt-2 inline-flex items-center gap-2 text-[13px] font-semibold text-violet hover:underline disabled:opacity-60"
                >
                  {loadingMore ? <Spinner className="h-3.5 w-3.5" /> : <Icon name="chevron-down" className="h-3.5 w-3.5" />}
                  Daha eski hareketler ({history.total - history.items.length})
                </button>
              ) : null}
            </>
          )}
        </section>
      </div>
    </Sheet>
  );
}
