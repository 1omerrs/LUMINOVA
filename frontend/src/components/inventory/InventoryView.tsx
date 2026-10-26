import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { ApiRequestError } from "../../lib/http.ts";
import {
  deleteProduct,
  fetchInventorySummary,
  fetchProduct,
  fetchProducts,
  formatQuantity,
  sortLabels,
  unitShort,
  type InventorySummary,
  type Paged,
  type Product,
  type ProductSort,
} from "../../lib/inventory.ts";
import { readOnly, type WorkspaceModule } from "../../lib/modules.ts";
import { useWorkspace } from "../../lib/workspace.ts";
import { Alert, Button, Spinner } from "../forms/Controls.tsx";
import { ConfirmDialog } from "../ui/ConfirmDialog.tsx";
import { Icon } from "../ui/Icon.tsx";
import { Pagination } from "../ui/Pagination.tsx";
import { ModuleIcon } from "../workspace/ModuleIcon.tsx";
import { ProductEditor } from "./ProductEditor.tsx";
import { ReorderPanel } from "./ReorderPanel.tsx";
import { StockSheet } from "./StockSheet.tsx";

const PAGE_SIZE = 20;

type Load = { status: "loading" } | { status: "ready"; data: Paged<Product> } | { status: "failed"; message: string };

function StockLevel({ product }: { product: Product }) {
  const stock = Number(product.stock_quantity);
  const minimum = Number(product.min_stock);
  const ratio = minimum > 0 ? Math.min(stock / (minimum * 2), 1) : stock > 0 ? 1 : 0;
  const tone = product.critical ? "text-error-text" : product.low ? "text-warning-text" : "";
  const bar = product.critical ? "bg-error" : product.low ? "bg-warning" : "bg-violet/70";
  return (
    <div className="min-w-[120px]">
      <p className={`text-[14px] font-semibold tabular-nums ${tone}`}>
        {formatQuantity(stock)} <span className="text-[12px] font-medium text-slate">{unitShort(product.unit)}</span>
      </p>
      {minimum > 0 ? (
        <div className="mt-1.5 h-1 w-full max-w-[120px] overflow-hidden rounded-full bg-mist/70" aria-hidden>
          <div className={`h-full rounded-full ${bar}`} style={{ width: `${Math.max(ratio * 100, stock > 0 ? 4 : 0)}%` }} />
        </div>
      ) : null}
    </div>
  );
}

function LevelBadge({ product }: { product: Product }) {
  if (product.critical) return <span className="shrink-0 rounded-full bg-error/10 px-2 py-0.5 text-[11px] font-semibold text-error-text">Kritik</span>;
  if (product.low) return <span className="shrink-0 rounded-full bg-warning/10 px-2 py-0.5 text-[11px] font-semibold text-warning-text">Azaldı</span>;
  return null;
}

export function InventoryView({ module }: { module: WorkspaceModule }) {
  const { refreshFeed, modules } = useWorkspace();
  const productionOn = modules.some((item) => item.key === "production" && item.enabled);
  const [params, setParams] = useSearchParams();
  const lowOnly = params.get("kritik") === "1";
  const [input, setInput] = useState("");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<ProductSort>("-created_at");
  const [page, setPage] = useState(1);
  const [reload, setReload] = useState(0);
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [summary, setSummary] = useState<InventorySummary | null>(null);
  const [editing, setEditing] = useState<{ product: Product | null } | null>(null);
  const [moving, setMoving] = useState<Product | null>(null);
  const [removing, setRemoving] = useState<Product | null>(null);
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
    Promise.all([fetchProducts({ q: search, sort, low: lowOnly, page, pageSize: PAGE_SIZE }), fetchInventorySummary()])
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
        if (!cancelled) setLoad({ status: "failed", message: error instanceof ApiRequestError ? error.message : "Ürünler yüklenemedi." });
      });
    return () => {
      cancelled = true;
    };
  }, [search, sort, lowOnly, page, reload]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 4000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  function refresh() {
    setReload((value) => value + 1);
  }

  function showLow(next: boolean) {
    setPage(1);
    setParams(next ? { kritik: "1" } : {}, { replace: true });
  }

  const data = load.status === "ready" ? load.data : null;
  const emptyWorkspace = summary !== null && summary.products === 0;

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-4">
          <div className="min-w-0">
            <h1 className="font-display text-[22px] font-semibold tracking-[-0.02em] text-midnight sm:text-[24px]">{module.name}</h1>
            <p className="mt-0.5 text-[14px] text-slate">
              {summary ? (
                <>
                  {summary.products} ürün
                  {summary.critical > 0 ? <span className="font-medium text-error-text"> · {summary.critical} ürün kritik seviyede</span> : null}
                  {summary.low > summary.critical ? (
                    <span className="font-medium text-warning-text"> · {summary.low - summary.critical} ürün minimumun altında</span>
                  ) : null}
                  {summary.low === 0 && summary.critical === 0 ? " · azalan ürün yok" : null}
                </>
              ) : (
                module.summary
              )}
            </p>
          </div>
        </div>
        {emptyWorkspace || readOnly(module) ? null : (
          <Button size="lg" onClick={() => setEditing({ product: null })}>
            <Icon name="plus" className="h-4 w-4" strokeWidth={2} />
            Ürün ekle
          </Button>
        )}
      </section>

      {notice ? <Alert tone="success">{notice}</Alert> : null}

      {emptyWorkspace ? null : (
        <ReorderPanel
          reload={reload}
          productionOn={productionOn}
          onReceived={(message) => {
            setNotice(message);
            refresh();
            refreshFeed();
          }}
          onRestock={(productId) => {
            const local = data?.items.find((item) => item.id === productId);
            if (local) setMoving(local);
            else fetchProduct(productId).then(setMoving, () => undefined);
          }}
        />
      )}

      {emptyWorkspace ? (
        <section className="rounded-2xl border border-mist/80 bg-surface px-6 py-16 text-center">
          <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-paper text-ink-soft ring-1 ring-inset ring-mist">
            <ModuleIcon name="inventory" className="h-6 w-6" />
          </span>
          <h2 className="mt-5 text-[16px] font-semibold">İlk ürününüzü ekleyin.</h2>
          <p className="mx-auto mt-2 max-w-md text-[14px] leading-6 text-slate">
            Ürünlerinizi stok koduyla tanımlayın, minimum seviyeyi belirleyin. Girişler, çıkışlar ve sayımlar hareket geçmişine yazılır.
          </p>
          <Button className="mt-6" onClick={() => setEditing({ product: null })}>
            <Icon name="plus" className="h-4 w-4" strokeWidth={2} />
            Ürün ekle
          </Button>
        </section>
      ) : (
        <section className="overflow-hidden rounded-2xl border border-mist/80 bg-surface">
          <div className="flex flex-col gap-3 border-b border-mist/70 px-4 py-3 lg:flex-row lg:items-center lg:justify-between sm:px-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <div role="tablist" aria-label="Ürün filtresi" className="inline-flex rounded-xl bg-cloud p-1">
                {[
                  { value: false, label: "Tümü" },
                  { value: true, label: `Azalan stok${summary && summary.low > 0 ? ` (${summary.low})` : ""}` },
                ].map((tab) => (
                  <button
                    key={String(tab.value)}
                    type="button"
                    role="tab"
                    aria-selected={lowOnly === tab.value}
                    onClick={() => showLow(tab.value)}
                    className={`h-8 rounded-[9px] px-3 text-[13px] font-semibold transition-colors ${
                      lowOnly === tab.value ? "bg-surface text-graphite shadow-[0_1px_3px_rgba(16,19,28,0.12)]" : "text-slate hover:text-graphite"
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
              <label className="relative block w-full sm:w-72">
                <span className="sr-only">Ürün ara</span>
                <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate" />
                <input
                  type="search"
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  placeholder="Ürün adı veya stok kodu ara"
                  className="h-10 w-full rounded-lg border border-mist bg-surface pl-9 pr-3 text-[14px] outline-none transition-[border-color,box-shadow] placeholder:text-slate/70 hover:border-stone focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)]"
                />
              </label>
            </div>
            <label className="flex items-center gap-2 text-[13px] text-slate">
              Sırala
              <select
                aria-label="Sırala"
                value={sort}
                onChange={(event) => {
                  setSort(event.target.value as ProductSort);
                  setPage(1);
                }}
                className="h-10 rounded-lg border border-mist bg-surface px-3 text-[14px] text-graphite outline-none hover:border-stone focus:border-violet"
              >
                {(Object.keys(sortLabels) as ProductSort[]).map((key) => (
                  <option key={key} value={key}>
                    {sortLabels[key]}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {load.status === "failed" ? (
            <div className="px-5 py-10">
              <Alert tone="error">
                {load.message}{" "}
                <button type="button" onClick={refresh} className="font-semibold underline">
                  Tekrar dene
                </button>
              </Alert>
            </div>
          ) : !data ? (
            <p role="status" className="flex items-center gap-2.5 px-5 py-12 text-[14px] text-slate">
              <Spinner className="h-4 w-4 text-violet" /> Ürünler yükleniyor.
            </p>
          ) : data.items.length === 0 ? (
            <div className="px-5 py-14 text-center">
              <p className="text-[15px] font-semibold">{lowOnly && !search ? "Kritik seviyede ürün yok." : `“${search}” ile eşleşen ürün yok.`}</p>
              <p className="mt-1 text-[13px] text-slate">{lowOnly && !search ? "Stoklarınız minimum seviyelerin üzerinde." : "Farklı bir ad veya stok kodu deneyin."}</p>
              {search ? (
                <button type="button" onClick={() => setInput("")} className="mt-4 text-[14px] font-semibold text-violet hover:underline">
                  Aramayı temizle
                </button>
              ) : null}
            </div>
          ) : (
            <>
              <table className="hidden w-full text-left md:table">
                <thead className="bg-cloud/60 text-[12px] text-slate">
                  <tr>
                    <th scope="col" className="px-5 py-2.5 font-medium">Ürün</th>
                    <th scope="col" className="px-3 py-2.5 font-medium">Stok</th>
                    <th scope="col" className="whitespace-nowrap px-3 py-2.5 font-medium">Kullanılabilir</th>
                    <th scope="col" className="px-3 py-2.5 font-medium">Minimum</th>
                    <th scope="col" className="px-5 py-2.5 text-right font-medium">
                      <span className="sr-only">İşlemler</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-mist/60 text-[14px]">
                  {data.items.map((product) => (
                    <tr key={product.id} className="transition-colors hover:bg-cloud/50">
                      <td className="max-w-[320px] px-5 py-3">
                        <p className="flex items-center gap-2">
                          <span className="truncate font-semibold">{product.name}</span>
                          <LevelBadge product={product} />
                        </p>
                        <p className="font-mono text-[12px] text-slate">{product.sku}</p>
                      </td>
                      <td className="px-3 py-3">
                        <StockLevel product={product} />
                      </td>
                      <td className="whitespace-nowrap px-3 py-3 text-[13px] tabular-nums">
                        {Number(product.incoming) > 0 ? (
                          <span className="mb-0.5 block text-[12px] text-violet">+{formatQuantity(product.incoming)} üretimde</span>
                        ) : null}
                        {Number(product.reserved) > 0 ? (
                          <span title="Onaylanmış siparişler ve açık iş emirleri için ayrılan miktar">
                            <span className="text-slate">{formatQuantity(product.reserved)} ayrılmış · </span>
                            <span className={Number(product.available) < 0 ? "font-semibold text-error-text" : "font-semibold text-graphite"}>
                              {formatQuantity(product.available)} {unitShort(product.unit)}
                            </span>
                          </span>
                        ) : (
                          <span className="text-slate">—</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-3 py-3 tabular-nums text-slate">
                        {Number(product.min_stock) > 0 ? `${formatQuantity(product.min_stock)} ${unitShort(product.unit)}` : "—"}
                        {product.critical_level !== null ? (
                          <span className="block text-[12px]">kritik {formatQuantity(product.critical_level)}</span>
                        ) : null}
                      </td>
                      <td className="px-5 py-3">
                        <RowActions product={product} onMove={() => setMoving(product)} onEdit={() => setEditing({ product })} onRemove={() => setRemoving(product)} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <ul className="divide-y divide-mist/60 md:hidden">
                {data.items.map((product) => (
                  <li key={product.id} className="flex items-center gap-3 px-4 py-3.5">
                    <div className="min-w-0 flex-1">
                      <p className="flex items-center gap-2">
                        <span className="truncate text-[14px] font-semibold">{product.name}</span>
                        <LevelBadge product={product} />
                      </p>
                      <p className="mt-0.5 text-[13px] text-slate">
                        <span className="font-mono text-[12px]">{product.sku}</span> ·{" "}
                        <span className="tabular-nums text-graphite">
                          {formatQuantity(product.stock_quantity)} {unitShort(product.unit)}
                        </span>
                        {Number(product.reserved) > 0 ? (
                          <span className={Number(product.available) < 0 ? "text-error-text" : ""}>
                            {" "}
                            · kullanılabilir {formatQuantity(product.available)}
                          </span>
                        ) : null}
                      </p>
                    </div>
                    <RowActions product={product} onMove={() => setMoving(product)} onEdit={() => setEditing({ product })} onRemove={() => setRemoving(product)} />
                  </li>
                ))}
              </ul>

              <Pagination page={data.page} pageSize={data.page_size} total={data.total} noun="ürün" onPage={setPage} />
            </>
          )}
        </section>
      )}

      {editing ? (
        <ProductEditor
          key={editing.product?.id ?? "new"}
          product={editing.product}
          onClose={() => setEditing(null)}
          onSaved={(product, created) => {
            setEditing(null);
            setNotice(created ? `${product.name} eklendi.` : `${product.name} güncellendi.`);
            if (created) {
              setInput("");
              setSearch("");
              setSort("-created_at");
              setPage(1);
              if (lowOnly && !product.low) showLow(false);
            }
            refresh();
          }}
        />
      ) : null}

      {moving ? (
        <StockSheet
          key={moving.id}
          product={moving}
          onClose={() => {
            setMoving(null);
            refresh();
          }}
          onChanged={(product) => {
            setLoad((current) =>
              current.status === "ready"
                ? { ...current, data: { ...current.data, items: current.data.items.map((item) => (item.id === product.id ? product : item)) } }
                : current,
            );
            void refreshFeed();
          }}
        />
      ) : null}

      {removing ? (
        <ConfirmDialog
          title="Ürün silinsin mi?"
          confirmLabel="Ürünü sil"
          pendingLabel="Siliniyor"
          onClose={() => setRemoving(null)}
          onConfirm={async () => {
            await deleteProduct(removing.id);
            setNotice(`${removing.name} silindi.`);
            setRemoving(null);
            refresh();
          }}
        >
          <span className="font-medium text-graphite">{removing.name}</span> listeden kaldırılır. Stok hareketleri ve denetim kaydı silinmez.
        </ConfirmDialog>
      ) : null}
    </div>
  );
}

function RowActions({ product, onMove, onEdit, onRemove }: { product: Product; onMove: () => void; onEdit: () => void; onRemove: () => void }) {
  const icon = "grid h-8 w-8 place-items-center rounded-lg text-slate transition-colors hover:bg-cloud hover:text-graphite";
  return (
    <div className="flex items-center justify-end gap-1">
      <button
        type="button"
        onClick={onMove}
        aria-label={`${product.name} için stok hareketi`}
        className="mr-1 inline-flex h-8 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg px-2.5 text-[13px] font-semibold text-violet ring-1 ring-inset ring-violet/25 transition-colors hover:bg-violet/[0.06]"
      >
        <span aria-hidden className="text-[14px] leading-none">±</span>
        <span className="hidden xl:inline">Stok hareketi</span>
      </button>
      <button type="button" onClick={onEdit} aria-label={`${product.name} düzenle`} className={icon}>
        <Icon name="pencil" className="h-4 w-4" />
      </button>
      <button type="button" onClick={onRemove} aria-label={`${product.name} sil`} className={`${icon} hover:bg-error/[0.06] hover:text-error-text`}>
        <Icon name="trash" className="h-4 w-4" />
      </button>
    </div>
  );
}
