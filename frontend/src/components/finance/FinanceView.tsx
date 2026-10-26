import { useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";
import {
  fetchFinanceSummary,
  fetchRecords,
  monthRange,
  sortLabels,
  statusLabel,
  statusTone,
  type CurrencyTotals,
  type FinanceRecord,
  type FinanceSummary,
  type RecordKind,
  type RecordPage,
  type RecordSort,
  type RecordStatus,
} from "../../lib/finance.ts";
import { ApiRequestError } from "../../lib/http.ts";
import { readOnly, type WorkspaceModule } from "../../lib/modules.ts";
import { formatMoney } from "../../lib/sales.ts";
import { formatDay } from "../../lib/tasks.ts";
import { useWorkspace } from "../../lib/workspace.ts";
import { Alert, Button, Spinner } from "../forms/Controls.tsx";
import { Icon } from "../ui/Icon.tsx";
import { Pagination } from "../ui/Pagination.tsx";
import { BalancesView, CashflowView, DueView } from "./FinanceViews.tsx";
import { RecordEditor } from "./RecordEditor.tsx";
import { RecordSheet } from "./RecordSheet.tsx";

const PAGE_SIZE = 25;
const statusOptions: { value: RecordStatus | null; label: string }[] = [
  { value: null, label: "Tüm durumlar" },
  { value: "pending", label: "Bekleyenler" },
  { value: "partial", label: "Kısmen ödenenler" },
  { value: "paid", label: "Ödenenler" },
  { value: "cancelled", label: "İptal edilenler" },
];
type Load = { status: "loading" } | { status: "ready"; data: RecordPage } | { status: "failed"; message: string };
type View = "kayitlar" | "vadeler" | "nakit" | "bakiyeler";
const views: { key: View; label: string }[] = [
  { key: "kayitlar", label: "Kayıtlar" },
  { key: "vadeler", label: "Vadeler" },
  { key: "nakit", label: "Nakit akışı" },
  { key: "bakiyeler", label: "Müşteri bakiyeleri" },
];

export function FinanceView({ module }: { module: WorkspaceModule }) {
  const { modules } = useWorkspace();
  const customersOn = modules.some((item) => item.key === "customers" && item.enabled);
  const [today, setToday] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [kind, setKind] = useState<RecordKind | null>(null);
  const [status, setStatus] = useState<RecordStatus | null>(null);
  const [overdue, setOverdue] = useState(false);
  const [input, setInput] = useState("");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<RecordSort>("-record_date");
  const [page, setPage] = useState(1);
  const [reload, setReload] = useState(0);
  const [summary, setSummary] = useState<FinanceSummary | null>(null);
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [editing, setEditing] = useState<{ record: FinanceRecord | null; kind?: RecordKind } | null>(null);
  const [viewing, setViewing] = useState<string | null>(null);
  const [notice, setNotice] = useState("");

  const period = today ? monthRange(today, offset) : null;
  const periodFrom = period?.from ?? null;
  const periodTo = period?.to ?? null;
  const allTime = overdue || status === "pending" || status === "partial";
  const [params, setParams] = useSearchParams();
  const view = (views.some((item) => item.key === params.get("gorunum")) ? params.get("gorunum") : "kayitlar") as View;

  useEffect(() => {
    const next = input.trim();
    if (next === search) return;
    const timer = window.setTimeout(() => {
      setSearch(next);
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [input, search]);

  useEffect(() => {
    let cancelled = false;
    fetchFinanceSummary(periodFrom && periodTo ? { from: periodFrom, to: periodTo } : undefined)
      .then((found) => {
        if (cancelled) return;
        setSummary(found);
        setToday((current) => current ?? found.today);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [periodFrom, periodTo, reload]);

  useEffect(() => {
    if (!periodFrom || !periodTo) return;
    let cancelled = false;
    fetchRecords({
      q: search,
      kind,
      status,
      overdue,
      from: allTime ? null : periodFrom,
      to: allTime ? null : periodTo,
      sort,
      page,
      pageSize: PAGE_SIZE,
    })
      .then((data) => {
        if (cancelled) return;
        if (data.items.length === 0 && data.page > 1) {
          setPage(data.page - 1);
          return;
        }
        setLoad({ status: "ready", data });
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoad({ status: "failed", message: error instanceof ApiRequestError ? error.message : "Kayıtlar yüklenemedi." });
      });
    return () => {
      cancelled = true;
    };
  }, [periodFrom, periodTo, search, kind, status, overdue, allTime, sort, page, reload]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 4000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const data = load.status === "ready" ? load.data : null;
  const main = summary?.totals.find((row) => row.currency === "TRY") ?? null;
  const others = summary?.totals.filter((row) => row.currency !== "TRY") ?? [];

  function resetPage<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value);
      setPage(1);
    };
  }

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-4">
          <div className="min-w-0">
            <h1 className="font-display text-[22px] font-semibold tracking-[-0.02em] text-midnight sm:text-[24px]">{module.name}</h1>
            <p className="mt-0.5 text-[14px] text-slate">{module.summary}</p>
          </div>
        </div>
        <div className={`flex gap-2 ${readOnly(module) ? "hidden" : ""}`}>
          <Button size="lg" variant="quiet" onClick={() => setEditing({ record: null, kind: "expense" })} disabled={!today}>
            <Icon name="plus" className="h-4 w-4" strokeWidth={2} />
            Gider ekle
          </Button>
          <Button size="lg" onClick={() => setEditing({ record: null, kind: "income" })} disabled={!today}>
            <Icon name="plus" className="h-4 w-4" strokeWidth={2} />
            Gelir ekle
          </Button>
        </div>
      </section>

      {notice ? <Alert tone="success">{notice}</Alert> : null}

      <nav aria-label="Finans görünümü" className="flex gap-5 overflow-x-auto overflow-y-hidden border-b border-hairline [scrollbar-width:none]">
        {views.map((item) => (
          <button
            key={item.key}
            type="button"
            aria-current={view === item.key ? "page" : undefined}
            onClick={() => setParams(item.key === "kayitlar" ? {} : { gorunum: item.key }, { replace: true })}
            className={`-mb-px shrink-0 border-b-2 pb-2.5 text-[14px] font-semibold transition-colors ${
              view === item.key ? "border-midnight text-midnight" : "border-transparent text-slate hover:text-graphite"
            }`}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {view === "vadeler" && today ? <DueView today={today} reload={reload} onOpen={setViewing} /> : null}
      {view === "nakit" ? <CashflowView reload={reload} /> : null}
      {view === "bakiyeler" ? <BalancesView reload={reload} customersOn={customersOn} /> : null}

      {view !== "kayitlar" ? null : (
        <>
      <section aria-labelledby="period-title" className="rounded-2xl border border-mist/80 bg-surface">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-mist/70 px-4 py-3 sm:px-5">
          <div className="flex items-center gap-1">
            <button
              type="button"
              aria-label="Önceki ay"
              onClick={() => resetPage(setOffset)(offset - 1)}
              className="grid h-9 w-9 place-items-center rounded-lg text-slate transition-colors hover:bg-cloud hover:text-graphite"
            >
              <Icon name="chevron-left" className="h-4 w-4" />
            </button>
            <h2 id="period-title" className="min-w-[132px] text-center text-[15px] font-semibold capitalize" aria-live="polite">
              {period?.label ?? "Dönem"}
            </h2>
            <button
              type="button"
              aria-label="Sonraki ay"
              onClick={() => resetPage(setOffset)(offset + 1)}
              className="grid h-9 w-9 place-items-center rounded-lg text-slate transition-colors hover:bg-cloud hover:text-graphite"
            >
              <Icon name="chevron-right" className="h-4 w-4" />
            </button>
            {offset !== 0 ? (
              <button type="button" onClick={() => resetPage(setOffset)(0)} className="ml-1 text-[13px] font-semibold text-violet hover:underline">
                Bu aya dön
              </button>
            ) : null}
          </div>
          <p className="text-[12px] text-slate">Gelir ve gider kayıt tarihine göre; alacak ve borç tüm dönemlerin açık kayıtlarıdır.</p>
        </div>
        {main ? (
          <div className="grid grid-cols-2 divide-mist/60 lg:grid-cols-5 lg:divide-x">
            <Metric label="Gelir" value={formatMoney(main.income, "TRY")} tone="text-success-text" extra={others.map((row) => formatMoney(row.income, row.currency))} />
            <Metric label="Gider" value={formatMoney(main.expense, "TRY")} extra={others.map((row) => formatMoney(row.expense, row.currency))} />
            <Metric
              label="Net"
              value={formatMoney(main.net, "TRY")}
              tone={Number(main.net) < 0 ? "text-error-text" : "text-graphite"}
              extra={others.map((row) => formatMoney(row.net, row.currency))}
              bar={<Balance totals={main} />}
            />
            <Metric
              label="Açık alacak"
              value={formatMoney(main.receivable, "TRY")}
              extra={others.map((row) => formatMoney(row.receivable, row.currency))}
              note={summary && summary.overdue_receivables > 0 ? `${summary.overdue_receivables} kaydın vadesi geçti` : undefined}
            />
            <Metric
              label="Açık borç"
              value={formatMoney(main.payable, "TRY")}
              extra={others.map((row) => formatMoney(row.payable, row.currency))}
              note={summary && summary.overdue_payables > 0 ? `${summary.overdue_payables} ödemenin vadesi geçti` : undefined}
            />
          </div>
        ) : (
          <p role="status" className="flex items-center gap-2.5 px-5 py-8 text-[14px] text-slate">
            <Spinner className="h-4 w-4 text-violet" /> Özet hesaplanıyor.
          </p>
        )}
      </section>

      <section className="overflow-hidden rounded-2xl border border-mist/80 bg-surface">
        <div className="flex flex-col gap-3 border-b border-mist/70 px-4 py-3 sm:px-5 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <div role="tablist" aria-label="Kayıt türü" className="flex gap-1 rounded-xl bg-cloud p-1">
              {([null, "income", "expense"] as (RecordKind | null)[]).map((value) => (
                <button
                  key={value ?? "all"}
                  type="button"
                  role="tab"
                  aria-selected={kind === value}
                  onClick={() => resetPage(setKind)(value)}
                  className={`h-8 rounded-[9px] px-3 text-[13px] font-semibold transition-colors ${
                    kind === value ? "bg-surface text-graphite shadow-[0_1px_3px_rgba(16,19,28,0.12)]" : "text-slate hover:text-graphite"
                  }`}
                >
                  {value === "income" ? "Gelirler" : value === "expense" ? "Giderler" : "Tümü"}
                </button>
              ))}
            </div>
            <select
              aria-label="Durum"
              value={status ?? ""}
              onChange={(event) => resetPage(setStatus)((event.target.value || null) as RecordStatus | null)}
              className="h-10 rounded-lg border border-mist bg-surface px-3 text-[14px] text-graphite outline-none hover:border-stone focus:border-violet"
            >
              {statusOptions.map((option) => (
                <option key={option.label} value={option.value ?? ""}>
                  {option.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              aria-pressed={overdue}
              onClick={() => resetPage(setOverdue)(!overdue)}
              className={`h-10 rounded-lg px-3 text-[13px] font-semibold ring-1 ring-inset transition-colors ${
                overdue ? "bg-error/[0.06] text-error-text ring-error/30" : "bg-surface text-slate ring-mist hover:text-graphite"
              }`}
            >
              Vadesi geçenler
            </button>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <label className="relative block w-full sm:w-60">
              <span className="sr-only">Kayıt ara</span>
              <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate" />
              <input
                type="search"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="Açıklama veya karşı taraf"
                className="h-10 w-full rounded-lg border border-mist bg-surface pl-9 pr-3 text-[14px] outline-none placeholder:text-slate/70 hover:border-stone focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)]"
              />
            </label>
            <select
              aria-label="Sırala"
              value={sort}
              onChange={(event) => resetPage(setSort)(event.target.value as RecordSort)}
              className="h-10 rounded-lg border border-mist bg-surface px-3 text-[14px] text-graphite outline-none hover:border-stone focus:border-violet"
            >
              {(Object.keys(sortLabels) as RecordSort[]).map((key) => (
                <option key={key} value={key}>
                  {sortLabels[key]}
                </option>
              ))}
            </select>
          </div>
        </div>
        {allTime ? <p className="border-b border-mist/60 bg-cloud/50 px-5 py-2 text-[12px] text-slate">Bekleyen ve vadesi geçen kayıtlar tüm dönemlerden listelenir.</p> : null}

        {load.status === "failed" ? (
          <div className="px-5 py-10">
            <Alert tone="error">
              {load.message}{" "}
              <button type="button" onClick={() => setReload((value) => value + 1)} className="font-semibold underline">
                Tekrar dene
              </button>
            </Alert>
          </div>
        ) : !data ? (
          <p role="status" className="flex items-center gap-2.5 px-5 py-12 text-[14px] text-slate">
            <Spinner className="h-4 w-4 text-violet" /> Kayıtlar yükleniyor.
          </p>
        ) : data.items.length === 0 ? (
          <div className="px-5 py-14 text-center">
            <p className="text-[15px] font-semibold">{search ? `“${search}” ile eşleşen kayıt yok.` : allTime ? "Bekleyen kayıt yok." : "Bu dönemde kayıt yok."}</p>
            <p className="mx-auto mt-2 max-w-md text-[13px] leading-5 text-slate">
              Gelir ve giderlerinizi buraya girin. Satış siparişlerinden gelir kaydı, sipariş panelindeki “Gelir kaydı oluştur” düğmesiyle açılır.
            </p>
          </div>
        ) : (
          <>
            <ul className="divide-y divide-mist/60">
              {data.items.map((record) => (
                <li key={record.id}>
                  <RecordRow record={record} onOpen={() => setViewing(record.id)} />
                </li>
              ))}
            </ul>
            <Pagination page={data.page} pageSize={data.page_size} total={data.total} noun="kayıt" onPage={setPage} />
          </>
        )}
      </section>
        </>
      )}

      {editing && today ? (
        <RecordEditor
          key={editing.record?.id ?? `new-${editing.kind}`}
          record={editing.record}
          prefill={editing.kind ? { kind: editing.kind } : undefined}
          customersOn={customersOn}
          today={today}
          onClose={() => setEditing(null)}
          onSaved={(record, created) => {
            setEditing(null);
            setNotice(created ? `“${record.description}” eklendi.` : `“${record.description}” güncellendi.`);
            setReload((value) => value + 1);
            setViewing(record.id);
          }}
        />
      ) : null}

      {viewing && !editing && today ? (
        <RecordSheet
          key={viewing}
          recordId={viewing}
          today={today}
          onClose={() => setViewing(null)}
          onEdit={(record) => setEditing({ record })}
          onChanged={(_, message) => {
            setNotice(message);
            setReload((value) => value + 1);
          }}
        />
      ) : null}
    </div>
  );
}

function Metric({ label, value, tone = "text-graphite", extra, note, bar }: { label: string; value: string; tone?: string; extra: string[]; note?: string; bar?: ReactNode }) {
  return (
    <div className="min-w-0 border-b border-mist/60 px-4 py-4 last:border-b-0 sm:px-5 lg:border-b-0">
      <p className="text-[12px] font-medium text-slate">{label}</p>
      <p className={`mt-1 truncate text-[20px] font-semibold tabular-nums tracking-tight ${tone}`}>{value}</p>
      {extra.map((line) => (
        <p key={line} className="text-[12px] tabular-nums text-slate">
          + {line}
        </p>
      ))}
      {bar}
      {note ? <p className="mt-1 text-[12px] font-medium text-error-text">{note}</p> : null}
    </div>
  );
}

function Balance({ totals }: { totals: CurrencyTotals }) {
  const income = Number(totals.income);
  const expense = Number(totals.expense);
  const sum = income + expense;
  if (sum === 0) return null;
  return (
    <div aria-hidden className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-mist/60">
      <span className="h-full bg-success" style={{ width: `${(income / sum) * 100}%` }} />
      <span className="h-full bg-error/70" style={{ width: `${(expense / sum) * 100}%` }} />
    </div>
  );
}

function RecordRow({ record, onOpen }: { record: FinanceRecord; onOpen: () => void }) {
  const income = record.kind === "income";
  const party = record.customer_name ?? record.counterparty;
  return (
    <button
      type="button"
      onClick={onOpen}
      className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 px-4 py-3.5 text-left transition-colors hover:bg-cloud/50 sm:grid-cols-[92px_minmax(0,1fr)_150px_140px] sm:px-5"
    >
      <span className="order-3 text-[12px] text-slate sm:order-none sm:text-[13px]">{formatDay(record.record_date)}</span>
      <span className="order-1 min-w-0 sm:order-none">
        <span className={`block truncate text-[14px] font-medium ${record.status === "cancelled" ? "text-slate line-through decoration-slate/40" : ""}`}>{record.description}</span>
        <span className="block truncate text-[12px] text-slate">
          {[record.category, party, record.order_code].filter(Boolean).join(" · ")}
        </span>
      </span>
      <span className="order-4 justify-self-end sm:order-none sm:justify-self-start">
        <span className={`rounded-full px-2.5 py-0.5 text-[12px] font-semibold ${statusTone(record)}`}>{record.overdue ? "Vadesi geçti" : statusLabel(record)}</span>
      </span>
      <span
        className={`order-2 justify-self-end text-[15px] font-semibold tabular-nums sm:order-none ${
          record.status === "cancelled" ? "text-slate line-through decoration-slate/40" : income ? "text-success-text" : "text-graphite"
        }`}
      >
        {income ? "+" : "−"}
        {formatMoney(record.amount, record.currency)}
        {record.status === "partial" ? (
          <span className="block text-right text-[11.5px] font-medium text-slate">kalan {formatMoney(record.remaining, record.currency)}</span>
        ) : null}
      </span>
    </button>
  );
}
