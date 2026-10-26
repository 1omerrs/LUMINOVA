import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { fetchBalances, fetchCashflow, fetchRecords, saveOpeningBalance, statusLabel, type Balance, type Cashflow, type FinanceRecord, type RecordKind } from "../../lib/finance.ts";
import { ApiRequestError } from "../../lib/http.ts";
import { currencies, formatMoney, type Currency } from "../../lib/sales.ts";
import { formatDay } from "../../lib/tasks.ts";
import { Alert, Spinner } from "../forms/Controls.tsx";

const short = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "short", timeZone: "UTC" });
const day = (iso: string) => short.format(new Date(`${iso}T00:00:00Z`));
const plus = (iso: string, days: number) => new Date(Date.parse(`${iso}T00:00:00Z`) + days * 86_400_000).toISOString().slice(0, 10);

function Loading({ label }: { label: string }) {
  return (
    <p role="status" className="flex items-center gap-2.5 px-5 py-12 text-[14px] text-slate">
      <Spinner className="h-4 w-4 text-violet" /> {label}
    </p>
  );
}

type Bucket = { key: string; title: string; tone: string; items: FinanceRecord[] };

function bucketize(items: FinanceRecord[], today: string): Bucket[] {
  const week = plus(today, 7);
  const buckets: Bucket[] = [
    { key: "late", title: "Vadesi geçti", tone: "text-error-text", items: [] },
    { key: "week", title: "Bu hafta", tone: "text-warning-text", items: [] },
    { key: "later", title: "Daha sonra", tone: "text-slate", items: [] },
    { key: "none", title: "Vadesiz", tone: "text-slate", items: [] },
  ];
  for (const item of items) {
    const target = !item.due_date ? "none" : item.due_date < today ? "late" : item.due_date <= week ? "week" : "later";
    buckets.find((bucket) => bucket.key === target)?.items.push(item);
  }
  return buckets.filter((bucket) => bucket.items.length > 0);
}

function DueColumn({ kind, today, reload, onOpen }: { kind: RecordKind; today: string; reload: number; onOpen: (id: string) => void }) {
  const [items, setItems] = useState<FinanceRecord[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchRecords({ kind, open: true, sort: "due_date", pageSize: 100 })
      .then((page) => {
        if (!cancelled) setItems(page.items);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiRequestError ? caught.message : "Vadeler yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [kind, reload]);

  const totals = new Map<Currency, number>();
  for (const item of items ?? []) totals.set(item.currency, (totals.get(item.currency) ?? 0) + Number(item.remaining));

  return (
    <section aria-labelledby={`due-${kind}`} className="min-w-0 rounded-2xl border border-mist/80 bg-surface">
      <div className="flex items-baseline justify-between gap-3 border-b border-hairline px-5 py-3.5">
        <h2 id={`due-${kind}`} className="text-[12px] font-semibold uppercase tracking-[0.08em] text-slate">
          {kind === "income" ? "Tahsil edilecek" : "Ödenecek"}
        </h2>
        <p className="text-[14px] font-semibold tabular-nums">
          {[...totals.entries()].map(([currency, total]) => formatMoney(total, currency)).join(" · ") || formatMoney(0, "TRY")}
        </p>
      </div>
      {error ? (
        <div className="p-5">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : items === null ? (
        <Loading label="Vadeler yükleniyor." />
      ) : items.length === 0 ? (
        <p className="px-5 py-10 text-center text-[13.5px] text-slate">{kind === "income" ? "Bekleyen tahsilat yok." : "Bekleyen ödeme yok."}</p>
      ) : (
        bucketize(items, today).map((bucket) => (
          <div key={bucket.key}>
            <p className={`bg-cloud/50 px-5 py-1.5 text-[12px] font-semibold ${bucket.tone}`}>
              {bucket.title} · {bucket.items.length}
            </p>
            <ul className="divide-y divide-hairline">
              {bucket.items.map((item) => (
                <li key={item.id}>
                  <button type="button" onClick={() => onOpen(item.id)} className="flex w-full items-center gap-3 px-5 py-3 text-left hover:bg-cloud/40">
                    <span className="w-16 shrink-0 text-[12.5px] tabular-nums text-slate">{item.due_date ? day(item.due_date) : "—"}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[14px] font-medium">{item.description}</span>
                      <span className="block truncate text-[12px] text-slate">
                        {[item.customer_name ?? item.counterparty, item.status === "partial" ? statusLabel(item) : null].filter(Boolean).join(" · ")}
                      </span>
                    </span>
                    <span className="shrink-0 text-right text-[14px] font-semibold tabular-nums">{formatMoney(item.remaining, item.currency)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))
      )}
    </section>
  );
}

export function DueView({ today, reload, onOpen }: { today: string; reload: number; onOpen: (id: string) => void }) {
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <DueColumn kind="income" today={today} reload={reload} onOpen={onOpen} />
      <DueColumn kind="expense" today={today} reload={reload} onOpen={onOpen} />
    </div>
  );
}

export function CashflowView({ reload }: { reload: number }) {
  const [currency, setCurrency] = useState<Currency>("TRY");
  const [flow, setFlow] = useState<Cashflow | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchCashflow(currency)
      .then((next) => {
        if (!cancelled) setFlow(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiRequestError ? caught.message : "Nakit akışı yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [currency, reload]);

  if (error) return <Alert tone="error">{error}</Alert>;
  if (!flow || flow.currency !== currency) return <Loading label="Nakit akışı hesaplanıyor." />;

  const cash = flow.cash_now === null ? null : Number(flow.cash_now);
  const rows = flow.weeks.reduce<
    (Cashflow["weeks"][number] & { past: boolean; current: boolean; incoming: number; outgoing: number; net: number; running: number })[]
  >((list, week) => {
    const past = week.week_end < flow.today;
    const current = week.week_start <= flow.today && flow.today <= week.week_end;
    const incoming = past ? Number(week.actual_in) : Number(week.actual_in) + Number(week.expected_in);
    const outgoing = past ? Number(week.actual_out) : Number(week.actual_out) + Number(week.expected_out);
    const previous = list.length ? list[list.length - 1] : null;
    const before = previous && !previous.past ? previous.running : (cash ?? 0);
    // cash_now already contains this week's actual payments, so only the expected part is added on top of it.
    const change = cash === null ? incoming - outgoing : Number(week.expected_in) - Number(week.expected_out);
    list.push({ ...week, past, current, incoming, outgoing, net: incoming - outgoing, running: past ? 0 : before + change });
    return list;
  }, []);
  const peak = Math.max(1, ...rows.map((row) => Math.max(row.incoming, row.outgoing)));

  return (
    <div className="space-y-5">
      <CashStrip flow={flow} onSaved={setFlow} />
      <section className="rounded-2xl border border-mist/80 bg-surface">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hairline px-5 py-3.5">
          <h2 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-slate">Haftalık nakit akışı</h2>
          <div className="flex items-center gap-3">
            <p className="hidden text-[12px] text-slate md:block">Geçmiş haftalar gerçekleşen ödemeler, gelecek haftalar açık kayıtların vadesi</p>
            <select
              aria-label="Para birimi"
              value={currency}
              onChange={(event) => setCurrency(event.target.value as Currency)}
              className="h-9 rounded-lg border border-mist bg-surface px-2.5 text-[13px] outline-none focus:border-violet"
            >
              {currencies.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="grid grid-cols-2 divide-x divide-hairline border-b border-hairline text-[13px] sm:grid-cols-4">
          <Figure label="Gecikmiş alacak" value={formatMoney(flow.overdue_in, currency)} tone={Number(flow.overdue_in) > 0 ? "text-error-text" : undefined} />
          <Figure label="Gecikmiş borç" value={formatMoney(flow.overdue_out, currency)} tone={Number(flow.overdue_out) > 0 ? "text-error-text" : undefined} />
          <Figure label="Vadesiz alacak" value={formatMoney(flow.undated_in, currency)} />
          <Figure label="Vadesiz borç" value={formatMoney(flow.undated_out, currency)} />
        </div>
        <div className="overflow-x-auto px-5 pb-4 pt-5">
          <div className="flex min-w-[560px] items-end gap-2" style={{ height: 180 }}>
            {rows.map((row) => (
              <div key={row.week_start} className="flex h-full flex-1 flex-col justify-end">
                <div className="flex flex-1 items-end justify-center gap-1">
                  <Bar total={row.incoming} actual={Number(row.actual_in)} peak={peak} solid="bg-success/80" light="bg-success/35" label={`Giriş ${formatMoney(row.incoming, currency)}`} />
                  <Bar total={row.outgoing} actual={Number(row.actual_out)} peak={peak} solid="bg-error/70" light="bg-error/30" label={`Çıkış ${formatMoney(row.outgoing, currency)}`} />
                </div>
                <p className={`mt-1.5 text-center text-[11px] tabular-nums ${row.current ? "font-semibold text-midnight" : "text-slate"}`}>{day(row.week_start)}</p>
              </div>
            ))}
          </div>
          <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-slate">
            <li className="flex items-center gap-1.5">
              <span aria-hidden className="h-2.5 w-3 rounded-[2px] bg-success/80" /> Gerçekleşen giriş
            </li>
            <li className="flex items-center gap-1.5">
              <span aria-hidden className="h-2.5 w-3 rounded-[2px] bg-success/35" /> Beklenen giriş
            </li>
            <li className="flex items-center gap-1.5">
              <span aria-hidden className="h-2.5 w-3 rounded-[2px] bg-error/70" /> Gerçekleşen çıkış
            </li>
            <li className="flex items-center gap-1.5">
              <span aria-hidden className="h-2.5 w-3 rounded-[2px] bg-error/30" /> Beklenen çıkış
            </li>
          </ul>
        </div>
      </section>

      <section className="overflow-x-auto rounded-2xl border border-mist/80 bg-surface">
        <table className="w-full min-w-[560px] text-left text-[13.5px]">
          <thead className="bg-cloud/60 text-[12px] text-slate">
            <tr>
              <th scope="col" className="px-5 py-2.5 font-medium">Hafta</th>
              <th scope="col" className="px-3 py-2.5 text-right font-medium">Giriş</th>
              <th scope="col" className="px-3 py-2.5 text-right font-medium">Çıkış</th>
              <th scope="col" className="px-3 py-2.5 text-right font-medium">Net</th>
              <th scope="col" className="px-5 py-2.5 text-right font-medium">{cash === null ? "Bu haftadan itibaren toplam" : "Hafta sonu tahmini kasa"}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hairline">
            {rows.map((row) => {
              const running = row.running;
              return (
                <tr key={row.week_start} className={row.current ? "bg-violet-wash/40" : undefined}>
                  <td className="px-5 py-2.5">
                    {day(row.week_start)} – {day(row.week_end)}
                    <span className="ml-2 text-[12px] text-slate">{row.past ? "gerçekleşen" : row.current ? "bu hafta" : "beklenen"}</span>
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-success-text">{formatMoney(row.incoming, currency)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{formatMoney(row.outgoing, currency)}</td>
                  <td className={`px-3 py-2.5 text-right font-semibold tabular-nums ${row.net < 0 ? "text-error-text" : ""}`}>{formatMoney(row.net, currency)}</td>
                  <td className={`px-5 py-2.5 text-right tabular-nums ${row.past ? "text-slate" : running < 0 ? "font-semibold text-error-text" : "font-semibold"}`}>
                    {row.past ? "—" : formatMoney(running, currency)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="border-t border-hairline px-5 py-2.5 text-[12px] text-slate">
          {cash === null
            ? "Açılış bakiyesi girilmediği için toplam, yalnızca beklenen giriş ve çıkışların farkıdır. Gecikmiş kayıtlar tabloya dahil değildir."
            : "Tahmini kasa, açılış bakiyesine o tarihten sonraki tahsilat ve ödemelerin, gelecek haftalar için de vadesi gelen açık kayıtların eklenmesiyle hesaplanır. Gecikmiş kayıtlar dahil değildir."}
        </p>
      </section>
    </div>
  );
}

function CashStrip({ flow, onSaved }: { flow: Cashflow; onSaved: (flow: Cashflow) => void }) {
  const [editing, setEditing] = useState(false);
  const [amount, setAmount] = useState(flow.opening_amount ?? "");
  const [asOf, setAsOf] = useState(flow.opening_as_of ?? flow.today);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      onSaved(await saveOpeningBalance(flow.currency, amount.replace(",", "."), asOf));
      setEditing(false);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Açılış bakiyesi kaydedilemedi.");
    } finally {
      setSaving(false);
    }
  }

  const field = "h-9 rounded-lg border border-mist bg-surface px-2.5 text-[13.5px] outline-none focus:border-violet";
  return (
    <section aria-label="Kasa" className="rounded-2xl border border-mist/80 bg-surface px-5 py-4">
      {editing || flow.cash_now === null ? (
        <form onSubmit={save} className="flex flex-wrap items-end gap-3">
          <div className="min-w-[220px] flex-1">
            <p className="text-[14px] font-semibold">Kasa ve banka açılış bakiyesi</p>
            <p className="mt-0.5 text-[12.5px] text-slate">Bir tarihteki toplam nakit ve banka bakiyenizi girin; sonraki tahsilat ve ödemelerle tahmini kasa otomatik hesaplanır.</p>
          </div>
          <label className="text-[12px] text-slate">
            Tutar ({flow.currency})
            <input value={amount} onChange={(event) => setAmount(event.target.value)} inputMode="decimal" required placeholder="0,00" className={`mt-1 block w-36 ${field}`} />
          </label>
          <label className="text-[12px] text-slate">
            Tarih
            <input type="date" value={asOf} max={flow.today} onChange={(event) => setAsOf(event.target.value)} required className={`mt-1 block ${field}`} />
          </label>
          <button type="submit" disabled={saving} className="h-9 rounded-lg bg-midnight px-4 text-[13.5px] font-semibold text-onink disabled:opacity-60">
            {saving ? "Kaydediliyor" : "Kaydet"}
          </button>
          {editing ? (
            <button type="button" onClick={() => setEditing(false)} className="h-9 rounded-lg px-3 text-[13.5px] text-slate hover:bg-cloud">
              Vazgeç
            </button>
          ) : null}
          {error ? (
            <div className="basis-full">
              <Alert tone="error">{error}</Alert>
            </div>
          ) : null}
        </form>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-[12px] text-slate">Tahmini kasa (bugün)</p>
            <p className={`text-[22px] font-semibold tabular-nums ${Number(flow.cash_now) < 0 ? "text-error-text" : ""}`}>{formatMoney(flow.cash_now, flow.currency)}</p>
            <p className="text-[12px] text-slate">
              {formatDay(flow.opening_as_of ?? flow.today)} açılış bakiyesi {formatMoney(flow.opening_amount ?? "0", flow.currency)} üzerine hesaplandı
            </p>
          </div>
          <button type="button" onClick={() => setEditing(true)} className="h-9 rounded-lg border border-mist px-3.5 text-[13.5px] font-medium hover:bg-cloud">
            Açılış bakiyesini düzenle
          </button>
        </div>
      )}
    </section>
  );
}

function Bar({ total, actual, peak, solid, light, label }: { total: number; actual: number; peak: number; solid: string; light: string; label: string }) {
  const done = Math.min(actual, total);
  return (
    <span title={label} className="flex w-[42%] flex-col justify-end overflow-hidden rounded-t-[3px]" style={{ height: `${(total / peak) * 100}%`, minHeight: total > 0 ? 3 : 0 }}>
      {total > done ? <span className={light} style={{ flexGrow: total - done }} /> : null}
      {done > 0 ? <span className={solid} style={{ flexGrow: done }} /> : null}
    </span>
  );
}

function Figure({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="px-5 py-3">
      <p className="text-[12px] text-slate">{label}</p>
      <p className={`mt-0.5 font-semibold tabular-nums ${tone ?? ""}`}>{value}</p>
    </div>
  );
}

export function BalancesView({ reload, customersOn }: { reload: number; customersOn: boolean }) {
  const [rows, setRows] = useState<Balance[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchBalances()
      .then((next) => {
        if (!cancelled) setRows(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiRequestError ? caught.message : "Bakiyeler yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [reload]);

  if (error) return <Alert tone="error">{error}</Alert>;
  if (!rows) return <Loading label="Bakiyeler hesaplanıyor." />;
  if (rows.length === 0) {
    return <p className="rounded-2xl border border-mist/80 bg-surface px-5 py-12 text-center text-[14px] text-slate">Açık müşteri bakiyesi yok; bütün gelir kayıtları tahsil edildi.</p>;
  }

  return (
    <section className="overflow-x-auto rounded-2xl border border-mist/80 bg-surface">
      <table className="w-full min-w-[640px] text-left text-[13.5px]">
        <thead className="bg-cloud/60 text-[12px] text-slate">
          <tr>
            <th scope="col" className="px-5 py-2.5 font-medium">Müşteri</th>
            <th scope="col" className="px-3 py-2.5 text-right font-medium">Açık bakiye</th>
            <th scope="col" className="px-3 py-2.5 text-right font-medium">Vadesi geçen</th>
            <th scope="col" className="px-3 py-2.5 font-medium">En eski vade</th>
            <th scope="col" className="px-5 py-2.5 font-medium">Son tahsilat</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline">
          {rows.map((row) => (
            <tr key={`${row.customer_id ?? row.name}-${row.currency}`}>
              <td className="px-5 py-3">
                {row.customer_id && customersOn ? (
                  <Link to={`/panel/musteriler?musteri=${row.customer_id}`} className="font-semibold hover:text-violet">
                    {row.name}
                  </Link>
                ) : (
                  <span className="font-semibold">{row.name}</span>
                )}
                <span className="block text-[12px] text-slate">{row.records} açık kayıt</span>
              </td>
              <td className="px-3 py-3 text-right font-semibold tabular-nums">{formatMoney(row.open_amount, row.currency)}</td>
              <td className={`px-3 py-3 text-right tabular-nums ${Number(row.overdue_amount) > 0 ? "font-semibold text-error-text" : "text-slate"}`}>
                {Number(row.overdue_amount) > 0 ? formatMoney(row.overdue_amount, row.currency) : "—"}
              </td>
              <td className="px-3 py-3 tabular-nums text-slate">{row.oldest_due ? formatDay(row.oldest_due) : "—"}</td>
              <td className="px-5 py-3 tabular-nums text-slate">{row.last_payment ? formatDay(row.last_payment) : "Henüz yok"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
