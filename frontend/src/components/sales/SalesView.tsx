import { useEffect, useState } from "react";
import { ApiRequestError } from "../../lib/http.ts";
import { useCreateIntent, type IntentCustomer } from "../../lib/intent.ts";
import { readOnly, type WorkspaceModule } from "../../lib/modules.ts";
import {
  fetchOrders,
  fetchSalesSummary,
  formatDate,
  formatMoney,
  sortLabels,
  statusLabels,
  statusTone,
  type OrderDetail,
  type OrderSort,
  type OrderStatus,
  type OrderSummary,
  type SalesSummary,
} from "../../lib/sales.ts";
import { useWorkspace } from "../../lib/workspace.ts";
import { Alert, Button, Spinner } from "../forms/Controls.tsx";
import { Icon } from "../ui/Icon.tsx";
import { Pagination } from "../ui/Pagination.tsx";
import { ModuleIcon } from "../workspace/ModuleIcon.tsx";
import { OrderEditor } from "./OrderEditor.tsx";
import { OrderSheet } from "./OrderSheet.tsx";
import { SalesRulesSheet } from "./SalesRulesSheet.tsx";

const PAGE_SIZE = 20;
const tabs: { value: OrderStatus | null; label: string }[] = [
  { value: null, label: "Tümü" },
  { value: "draft", label: "Taslak" },
  { value: "confirmed", label: "Onaylandı" },
  { value: "fulfilled", label: "Teslim edildi" },
  { value: "cancelled", label: "İptal" },
];

type Page = { items: OrderSummary[]; total: number; page: number; page_size: number };
type Load = { status: "loading" } | { status: "ready"; data: Page } | { status: "failed"; message: string };

export function SalesView({ module }: { module: WorkspaceModule }) {
  const { refreshFeed, user } = useWorkspace();
  const [rulesOpen, setRulesOpen] = useState(false);
  const [input, setInput] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<OrderStatus | null>(null);
  const [sort, setSort] = useState<OrderSort>("-created_at");
  const [page, setPage] = useState(1);
  const [reload, setReload] = useState(0);
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [summary, setSummary] = useState<SalesSummary | null>(null);
  const intent = useCreateIntent();
  const [editing, setEditing] = useState<{ order: OrderDetail | null; customer?: IntentCustomer | null } | null>(() => (intent ? { order: null, customer: intent.customer } : null));
  const [viewing, setViewing] = useState<string | null>(null);
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
    Promise.all([fetchOrders({ q: search, status, sort, page, pageSize: PAGE_SIZE }), fetchSalesSummary()])
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
        if (!cancelled) setLoad({ status: "failed", message: error instanceof ApiRequestError ? error.message : "Siparişler yüklenemedi." });
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
  const totalOrders = summary ? summary.draft + summary.confirmed + summary.fulfilled + summary.cancelled : null;
  const emptyWorkspace = totalOrders === 0;

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-4">
          <div className="min-w-0">
            <h1 className="font-display text-[22px] font-semibold tracking-[-0.02em] text-midnight sm:text-[24px]">{module.name}</h1>
            <p className="mt-0.5 text-[14px] text-slate">
              {summary && totalOrders ? `${summary.draft} taslak · ${summary.confirmed} teslim bekliyor · ${summary.fulfilled} teslim edildi` : module.summary}
            </p>
          </div>
        </div>
        <div className={`flex items-center gap-2 ${readOnly(module) ? "hidden" : ""}`}>
          <Button size="lg" variant="quiet" onClick={() => setRulesOpen(true)}>
            <Icon name="settings" className="h-4 w-4" />
            Kurallar
          </Button>
          {emptyWorkspace ? null : (
            <Button size="lg" onClick={() => setEditing({ order: null })}>
              <Icon name="plus" className="h-4 w-4" strokeWidth={2} />
              Yeni sipariş
            </Button>
          )}
        </div>
      </section>
      {rulesOpen ? (
        <SalesRulesSheet
          canEdit={user.role === "owner" || user.role === "admin"}
          onClose={() => setRulesOpen(false)}
          onSaved={() => {
            setRulesOpen(false);
            setNotice("Satış kuralları kaydedildi.");
          }}
        />
      ) : null}

      {notice ? <Alert tone="success">{notice}</Alert> : null}

      {emptyWorkspace ? (
        <section className="rounded-2xl border border-mist/80 bg-surface px-6 py-16 text-center">
          <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-paper text-ink-soft ring-1 ring-inset ring-mist">
            <ModuleIcon name="sales" className="h-6 w-6" />
          </span>
          <h2 className="mt-5 text-[16px] font-semibold">İlk siparişinizi oluşturun.</h2>
          <p className="mx-auto mt-2 max-w-md text-[14px] leading-6 text-slate">
            Müşteri seçin, ürün veya hizmet satırlarını ekleyin. Sipariş teslim edildiğinde ürünler stoktan otomatik düşülür.
          </p>
          <Button className="mt-6" onClick={() => setEditing({ order: null })}>
            <Icon name="plus" className="h-4 w-4" strokeWidth={2} />
            Yeni sipariş
          </Button>
        </section>
      ) : (
        <section className="overflow-hidden rounded-2xl border border-mist/80 bg-surface">
          <div className="flex flex-col gap-3 border-b border-mist/70 px-4 py-3 sm:px-5 xl:flex-row xl:items-center xl:justify-between">
            <div role="tablist" aria-label="Sipariş durumu" className="flex gap-1 overflow-x-auto rounded-xl bg-cloud p-1">
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
                    className={`h-8 shrink-0 rounded-[9px] px-3 text-[13px] font-semibold transition-colors ${
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
                <span className="sr-only">Sipariş ara</span>
                <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate" />
                <input
                  type="search"
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  placeholder="Müşteri veya SP-0001"
                  className="h-10 w-full rounded-lg border border-mist bg-surface pl-9 pr-3 text-[14px] outline-none placeholder:text-slate/70 hover:border-stone focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)]"
                />
              </label>
              <label className="flex items-center gap-2 text-[13px] text-slate">
                Sırala
                <select
                  aria-label="Sırala"
                  value={sort}
                  onChange={(event) => {
                    setSort(event.target.value as OrderSort);
                    setPage(1);
                  }}
                  className="h-10 rounded-lg border border-mist bg-surface px-3 text-[14px] text-graphite outline-none hover:border-stone focus:border-violet"
                >
                  {(Object.keys(sortLabels) as OrderSort[]).map((key) => (
                    <option key={key} value={key}>
                      {sortLabels[key]}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>

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
              <Spinner className="h-4 w-4 text-violet" /> Siparişler yükleniyor.
            </p>
          ) : data.items.length === 0 ? (
            <div className="px-5 py-14 text-center">
              <p className="text-[15px] font-semibold">{search ? `“${search}” ile eşleşen sipariş yok.` : "Bu durumda sipariş yok."}</p>
              {search ? (
                <button type="button" onClick={() => setInput("")} className="mt-4 text-[14px] font-semibold text-violet hover:underline">
                  Aramayı temizle
                </button>
              ) : null}
            </div>
          ) : (
            <>
              <ul className="divide-y divide-mist/60">
                {data.items.map((order) => (
                  <li key={order.id}>
                    <button
                      type="button"
                      onClick={() => setViewing(order.id)}
                      className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 px-4 py-3.5 text-left transition-colors hover:bg-cloud/50 sm:grid-cols-[96px_minmax(0,1fr)_110px_140px_120px] sm:px-5"
                    >
                      <span className="font-mono text-[13px] font-semibold text-graphite sm:order-none">{order.code}</span>
                      <span className={`justify-self-end rounded-full px-2.5 py-0.5 text-[12px] font-semibold sm:order-last sm:justify-self-start ${statusTone[order.status]}`}>
                        {statusLabels[order.status]}
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-[14px] font-medium">{order.customer_name}</span>
                        <span className="block text-[12px] text-slate">{order.item_count} satır</span>
                      </span>
                      <span className="text-[13px] text-slate sm:text-[14px]">{formatDate(order.order_date)}</span>
                      <span className="justify-self-end text-[14px] font-semibold tabular-nums sm:justify-self-end">{formatMoney(order.total, order.currency)}</span>
                    </button>
                  </li>
                ))}
              </ul>
              <Pagination page={data.page} pageSize={data.page_size} total={data.total} noun="sipariş" onPage={setPage} />
            </>
          )}
        </section>
      )}

      {editing ? (
        <OrderEditor
          key={editing.order?.id ?? "new"}
          order={editing.order}
          initialCustomer={editing.customer ?? null}
          onClose={() => setEditing(null)}
          onSaved={(order) => {
            setEditing(null);
            setNotice(editing.order ? `${order.code} güncellendi.` : `${order.code} taslak olarak kaydedildi.`);
            setReload((value) => value + 1);
            setViewing(order.id);
          }}
        />
      ) : null}

      {viewing && !editing ? (
        <OrderSheet
          key={viewing}
          orderId={viewing}
          onClose={() => setViewing(null)}
          onEdit={(order) => setEditing({ order })}
          onChanged={(order) => {
            setNotice(`${order.code}: ${statusLabels[order.status]}.`);
            setReload((value) => value + 1);
            void refreshFeed();
          }}
        />
      ) : null}
    </div>
  );
}
