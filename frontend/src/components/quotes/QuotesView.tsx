import { useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";
import { ApiRequestError } from "../../lib/http.ts";
import { useCreateIntent, type IntentCustomer } from "../../lib/intent.ts";
import { readOnly, type WorkspaceModule } from "../../lib/modules.ts";
import {
  createQuote,
  fetchQuotes,
  fetchQuoteSummary,
  quoteSortLabels,
  quoteStatusLabels,
  quoteStatusTone,
  updateQuote,
  type QuoteDetail,
  type QuotePage,
  type QuoteSort,
  type QuoteStatus,
  type QuoteSummary,
} from "../../lib/quotes.ts";
import { formatDate, formatMoney } from "../../lib/sales.ts";
import { useWorkspace } from "../../lib/workspace.ts";
import { Alert, Button, Spinner } from "../forms/Controls.tsx";
import { LineItemsEditor } from "../sales/OrderEditor.tsx";
import { Icon } from "../ui/Icon.tsx";
import { Pagination } from "../ui/Pagination.tsx";
import { QuoteSheet } from "./QuoteSheet.tsx";

const PAGE_SIZE = 20;
const tabs: { value: QuoteStatus | null; label: string }[] = [
  { value: null, label: "Tümü" },
  { value: "draft", label: "Taslak" },
  { value: "sent", label: "Gönderildi" },
  { value: "accepted", label: "Kabul" },
  { value: "rejected", label: "Ret" },
];
type Load = { status: "loading" } | { status: "ready"; data: QuotePage } | { status: "failed"; message: string };

export function QuotesView({ module, switcher }: { module: WorkspaceModule; switcher: ReactNode }) {
  const { modules } = useWorkspace();
  const salesOn = modules.some((item) => item.key === "sales" && item.enabled);
  const inventoryOn = modules.some((item) => item.key === "inventory" && item.enabled);
  const [input, setInput] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<QuoteStatus | null>(null);
  const [sort, setSort] = useState<QuoteSort>("-created_at");
  const [page, setPage] = useState(1);
  const [reload, setReload] = useState(0);
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [summary, setSummary] = useState<QuoteSummary | null>(null);
  const intent = useCreateIntent();
  const [editing, setEditing] = useState<{ quote: QuoteDetail | null; customer?: IntentCustomer | null } | null>(() => (intent ? { quote: null, customer: intent.customer } : null));
  const [params, setParams] = useSearchParams();
  const [viewing, setViewing] = useState<string | null>(() => params.get("teklif"));

  function closeViewing() {
    setViewing(null);
    if (params.has("teklif")) {
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          next.delete("teklif");
          return next;
        },
        { replace: true },
      );
    }
  }
  const [notice, setNotice] = useState("");

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
    Promise.all([fetchQuotes({ q: search, status, sort, page, pageSize: PAGE_SIZE }), fetchQuoteSummary()])
      .then(([data, totals]) => {
        if (cancelled) return;
        if (data.items.length === 0 && data.page > 1) {
          setPage(data.page - 1);
          return;
        }
        setLoad({ status: "ready", data });
        setSummary(totals);
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoad({ status: "failed", message: error instanceof ApiRequestError ? error.message : "Teklifler yüklenemedi." });
      });
    return () => {
      cancelled = true;
    };
  }, [search, status, sort, page, reload]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 4000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const data = load.status === "ready" ? load.data : null;
  const total = summary ? summary.draft + summary.sent + summary.accepted + summary.rejected : null;
  const empty = total === 0;

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-4">
          <div className="min-w-0">
            <h1 className="font-display text-[22px] font-semibold tracking-[-0.02em] text-midnight sm:text-[24px]">{module.name}</h1>
            <p className="mt-0.5 text-[14px] text-slate">
              {summary && total
                ? `${summary.sent} yanıt bekleyen · ${summary.accepted} kabul edilen · bekleyen tutar ${formatMoney(summary.open_value, "TRY")}`
                : "Tekliflerinizi hazırlayın, durumlarını takip edin, kabul edilenleri siparişe çevirin."}
            </p>
          </div>
        </div>
        {empty || readOnly(module) ? null : (
          <Button size="lg" onClick={() => setEditing({ quote: null })}>
            <Icon name="plus" className="h-4 w-4" strokeWidth={2} />
            Yeni teklif
          </Button>
        )}
      </section>
      {switcher}

      {notice ? <Alert tone="success">{notice}</Alert> : null}

      {empty ? (
        <section className="rounded-2xl border border-mist/80 bg-surface px-6 py-16 text-center">
          <h2 className="text-[16px] font-semibold">İlk teklifinizi hazırlayın.</h2>
          <p className="mx-auto mt-2 max-w-md text-[14px] leading-6 text-slate">
            Müşteri seçin, ürün veya hizmet satırlarını girin. Kabul edilen teklif tek adımda satış siparişine dönüşür.
          </p>
          <Button className="mt-6" onClick={() => setEditing({ quote: null })}>
            <Icon name="plus" className="h-4 w-4" strokeWidth={2} />
            Yeni teklif
          </Button>
        </section>
      ) : (
        <section className="overflow-hidden rounded-2xl border border-mist/80 bg-surface">
          <div className="flex flex-col gap-3 border-b border-mist/70 px-4 py-3 sm:px-5 xl:flex-row xl:items-center xl:justify-between">
            <div role="tablist" aria-label="Teklif durumu" className="flex flex-wrap gap-1 rounded-xl bg-cloud p-1">
              {tabs.map((tab) => {
                const count = tab.value && summary ? summary[tab.value] : null;
                return (
                  <button
                    key={tab.label}
                    type="button"
                    role="tab"
                    aria-selected={status === tab.value}
                    onClick={() => {
                      setStatus(tab.value);
                      setPage(1);
                    }}
                    className={`h-8 rounded-[9px] px-3 text-[13px] font-semibold transition-colors ${
                      status === tab.value ? "bg-surface text-graphite shadow-[0_1px_3px_rgba(16,19,28,0.12)]" : "text-slate hover:text-graphite"
                    }`}
                  >
                    {tab.label}
                    {count ? <span className="ml-1 text-slate">{count}</span> : null}
                  </button>
                );
              })}
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <label className="relative block w-full sm:w-64">
                <span className="sr-only">Teklif ara</span>
                <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate" />
                <input
                  type="search"
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  placeholder="Müşteri veya TK-0001"
                  className="h-10 w-full rounded-lg border border-mist bg-surface pl-9 pr-3 text-[14px] outline-none placeholder:text-slate/70 hover:border-stone focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)]"
                />
              </label>
              <select
                aria-label="Sırala"
                value={sort}
                onChange={(event) => {
                  setSort(event.target.value as QuoteSort);
                  setPage(1);
                }}
                className="h-10 rounded-lg border border-mist bg-surface px-3 text-[14px] text-graphite outline-none hover:border-stone focus:border-violet"
              >
                {(Object.keys(quoteSortLabels) as QuoteSort[]).map((key) => (
                  <option key={key} value={key}>
                    {quoteSortLabels[key]}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {load.status === "failed" ? (
            <div className="px-5 py-10">
              <Alert tone="error">{load.message}</Alert>
            </div>
          ) : !data ? (
            <p role="status" className="flex items-center gap-2.5 px-5 py-12 text-[14px] text-slate">
              <Spinner className="h-4 w-4 text-violet" /> Teklifler yükleniyor.
            </p>
          ) : data.items.length === 0 ? (
            <p className="px-5 py-14 text-center text-[15px] font-semibold">{search ? `“${search}” ile eşleşen teklif yok.` : "Bu durumda teklif yok."}</p>
          ) : (
            <>
              <ul className="divide-y divide-mist/60">
                {data.items.map((quote) => (
                  <li key={quote.id}>
                    <button
                      type="button"
                      onClick={() => setViewing(quote.id)}
                      className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 px-4 py-3.5 text-left transition-colors hover:bg-cloud/50 sm:grid-cols-[96px_minmax(0,1fr)_130px_140px_130px] sm:px-5"
                    >
                      <span className="font-mono text-[13px] font-semibold">{quote.code}</span>
                      <span className="flex items-center gap-1.5 justify-self-end sm:order-last sm:justify-self-start">
                        <span className={`rounded-full px-2.5 py-0.5 text-[12px] font-semibold ${quoteStatusTone[quote.status]}`}>{quoteStatusLabels[quote.status]}</span>
                        {quote.order_code ? <span className="font-mono text-[11px] text-slate">{quote.order_code}</span> : null}
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-[14px] font-medium">{quote.customer_name}</span>
                        <span className="block text-[12px] text-slate">{quote.item_count} satır</span>
                      </span>
                      <span className={`text-[13px] ${quote.expired ? "font-medium text-warning-text" : "text-slate"}`}>
                        {quote.valid_until ? `${quote.expired ? "Süresi doldu" : "Geçerli"} · ${formatDate(quote.valid_until)}` : formatDate(quote.quote_date)}
                      </span>
                      <span className="justify-self-end text-[14px] font-semibold tabular-nums">{formatMoney(quote.total, quote.currency)}</span>
                    </button>
                  </li>
                ))}
              </ul>
              <Pagination page={data.page} pageSize={data.page_size} total={data.total} noun="teklif" onPage={setPage} />
            </>
          )}
        </section>
      )}

      {editing ? (
        <LineItemsEditor
          key={editing.quote?.id ?? "new"}
          document={editing.quote ? { ...editing.quote, date: editing.quote.quote_date } : null}
          labels={{
            title: editing.quote ? `${editing.quote.code} teklifini düzenle` : "Yeni teklif",
            description: "Teklif taslak olarak kaydedilir. Müşteriye ilettikten sonra gönderildi olarak işaretleyin.",
            date: "Teklif tarihi",
            save: editing.quote ? "Değişiklikleri kaydet" : "Taslağı kaydet",
            failed: "Teklif kaydedilemedi.",
          }}
          productsEnabled={inventoryOn}
          withValidity
          initialCustomer={editing.customer ?? null}
          onClose={() => setEditing(null)}
          save={async ({ date, ...rest }) => {
            const payload = { ...rest, quote_date: date };
            const saved = editing.quote ? await updateQuote(editing.quote.id, payload) : await createQuote(payload);
            setEditing(null);
            setNotice(editing.quote ? `${saved.code} güncellendi.` : `${saved.code} taslak olarak kaydedildi.`);
            setReload((value) => value + 1);
            setViewing(saved.id);
          }}
        />
      ) : null}

      {viewing && !editing ? (
        <QuoteSheet
          key={viewing}
          quoteId={viewing}
          salesOn={salesOn}
          onClose={closeViewing}
          onEdit={(quote) => setEditing({ quote })}
          onChanged={(quote, action) => {
            setNotice(action === "convert" ? `${quote.code} ${quote.order_code ?? ""} siparişine çevrildi.` : `${quote.code}: ${quoteStatusLabels[quote.status]}.`);
            setReload((value) => value + 1);
          }}
        />
      ) : null}
    </div>
  );
}
