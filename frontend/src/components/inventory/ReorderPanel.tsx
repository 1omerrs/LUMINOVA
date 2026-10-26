import { useEffect, useState } from "react";
import { Link } from "react-router";
import { ApiRequestError } from "../../lib/http.ts";
import { fetchReorder, formatQuantity, parseQuantity, recordMovement, unitShort, type ReorderSuggestion } from "../../lib/inventory.ts";

const SHOWN = 4;

export function ReorderPanel({
  reload,
  productionOn,
  onRestock,
  onReceived,
}: {
  reload: number;
  productionOn: boolean;
  onRestock: (productId: string) => void;
  onReceived: (message: string) => void;
}) {
  const [items, setItems] = useState<ReorderSuggestion[] | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [receiving, setReceiving] = useState<{ id: string; quantity: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function receive(item: ReorderSuggestion) {
    if (!receiving) return;
    const quantity = parseQuantity(receiving.quantity);
    if (quantity === null || Number(quantity) <= 0) return setError("Geçerli bir miktar girin.");
    setSaving(true);
    setError("");
    try {
      await recordMovement(item.product_id, { kind: "in", quantity, note: "Yeniden sipariş önerisinden mal kabul", idempotency_key: crypto.randomUUID() });
      setReceiving(null);
      onReceived(`${item.name}: ${formatQuantity(quantity)} ${unitShort(item.unit)} stoğa girdi.`);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Stok girişi kaydedilemedi.");
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    fetchReorder()
      .then((next) => {
        if (!cancelled) setItems(next);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, [reload]);

  if (!items || items.length === 0) return null;
  const visible = expanded ? items : items.slice(0, SHOWN);

  return (
    <section aria-labelledby="reorder-title" className="rounded-2xl border border-mist/80 bg-surface">
      <div className="flex items-baseline justify-between gap-3 border-b border-hairline px-5 py-3.5">
        <h2 id="reorder-title" className="text-[12px] font-semibold uppercase tracking-[0.08em] text-slate">
          Yeniden sipariş önerileri · {items.length}
        </h2>
        <p className="hidden text-[12px] text-slate sm:block">Ayrılan stok, üretimdeki miktar ve son 30 günlük çıkış hızına göre</p>
      </div>
      {error ? <p className="border-b border-hairline px-5 py-2 text-[13px] text-error-text">{error}</p> : null}
      <ul className="divide-y divide-hairline">
        {visible.map((item) => (
          <li key={item.product_id} className="flex flex-col gap-3 px-5 py-3.5 sm:flex-row sm:items-center">
            <div className="min-w-0 flex-1">
              <p className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-[14px] font-semibold">{item.name}</span>
                <span className="font-mono text-[12px] text-slate">{item.sku}</span>
                {item.days_left !== null && item.days_left < 14 ? (
                  <span className="text-[12px] font-semibold text-warning-text">≈ {item.days_left} gün yeter</span>
                ) : null}
              </p>
              <p className="mt-0.5 text-[12.5px] leading-5 text-slate">{item.reasons.join(" ")}</p>
            </div>
            <div className="flex shrink-0 items-center gap-3">
              <span className="text-right text-[13px] tabular-nums">
                <span className="block text-[11.5px] text-slate">{item.action === "produce" ? "Üretilmeli" : "Alınmalı"}</span>
                <span className="font-semibold">
                  {formatQuantity(item.suggested)} {unitShort(item.unit)}
                </span>
              </span>
              {item.action === "produce" && productionOn ? (
                <Link
                  to={`/panel/uretim?${new URLSearchParams({ yeni: "1", urun: item.product_id, urun_adi: item.name, birim: item.unit, miktar: item.suggested })}`}
                  className="inline-flex h-8 items-center rounded-lg bg-midnight px-3 text-[13px] font-semibold text-onink hover:bg-graphite"
                >
                  İş emri aç
                </Link>
              ) : receiving?.id === item.product_id ? (
                <span className="flex items-center gap-1.5">
                  <input
                    aria-label={`${item.name} giriş miktarı`}
                    inputMode="decimal"
                    value={receiving.quantity}
                    onChange={(event) => setReceiving({ id: item.product_id, quantity: event.target.value })}
                    className="h-8 w-20 rounded-lg border border-mist bg-surface px-2 text-right text-[13px] tabular-nums outline-none focus:border-violet"
                  />
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => void receive(item)}
                    className="inline-flex h-8 items-center rounded-lg bg-midnight px-3 text-[13px] font-semibold text-onink hover:bg-graphite disabled:opacity-60"
                  >
                    {saving ? "Kaydediliyor" : "Girişi kaydet"}
                  </button>
                  <button type="button" onClick={() => setReceiving(null)} className="px-1 text-[13px] text-slate hover:text-graphite">
                    Vazgeç
                  </button>
                </span>
              ) : (
                <span className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => setReceiving({ id: item.product_id, quantity: formatQuantity(item.suggested) })}
                    className="inline-flex h-8 items-center rounded-lg px-3 text-[13px] font-semibold text-violet ring-1 ring-inset ring-violet/25 hover:bg-violet/[0.06]"
                  >
                    Teslim alındı
                  </button>
                  <button type="button" onClick={() => onRestock(item.product_id)} className="px-1 text-[13px] text-slate hover:text-graphite">
                    Diğer
                  </button>
                </span>
              )}
            </div>
          </li>
        ))}
      </ul>
      {items.length > SHOWN ? (
        <button type="button" onClick={() => setExpanded((value) => !value)} className="w-full border-t border-hairline px-5 py-2.5 text-left text-[13px] font-semibold text-violet hover:bg-cloud/50">
          {expanded ? "Daha az göster" : `${items.length - SHOWN} öneri daha`}
        </button>
      ) : null}
    </section>
  );
}
