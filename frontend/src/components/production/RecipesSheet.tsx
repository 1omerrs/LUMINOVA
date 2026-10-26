import { useCallback, useEffect, useState } from "react";
import { ApiRequestError } from "../../lib/http.ts";
import { fetchProducts, formatQuantity, parseQuantity, unitShort, type Unit } from "../../lib/inventory.ts";
import { fetchRecipe, fetchRecipes, saveRecipe, type RecipeSummary } from "../../lib/production.ts";
import { Alert, Button, Spinner } from "../forms/Controls.tsx";
import { quickProduct } from "../../lib/quickCreate.ts";
import { Picker } from "../forms/Picker.tsx";
import { Icon } from "../ui/Icon.tsx";
import { Sheet } from "../ui/Sheet.tsx";
import type { ProductOption } from "./ProductionEditor.tsx";

type Line = { key: string; product: ProductOption | null; quantity: string };

const blank = (): Line => ({ key: crypto.randomUUID(), product: null, quantity: "" });

function useProductSearch() {
  return useCallback(async (q: string) => {
    const page = await fetchProducts({ q, pageSize: 8, sort: "name" });
    return page.items.map((item) => ({ id: item.id, label: item.name, meta: `${item.sku} · stok ${formatQuantity(item.stock_quantity)} ${unitShort(item.unit)}`, unit: item.unit }));
  }, []);
}

export function RecipesSheet({ onClose }: { onClose: () => void }) {
  const [recipes, setRecipes] = useState<RecipeSummary[] | null>(null);
  const [editing, setEditing] = useState<ProductOption | null | "new">(null);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchRecipes()
      .then((next) => {
        if (!cancelled) setRecipes(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiRequestError ? caught.message : "Reçeteler yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [version]);

  if (editing) {
    return (
      <RecipeEditor
        product={editing === "new" ? null : editing}
        onBack={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          setVersion((value) => value + 1);
        }}
      />
    );
  }

  return (
    <Sheet
      title="Ürün reçeteleri"
      description="Bir birim ürün için hangi malzemeden ne kadar gerektiğini tanımlayın. İş emri açarken malzemeler bu reçeteden miktara göre hesaplanır."
      onClose={onClose}
      footer={
        <Button onClick={() => setEditing("new")}>
          <Icon name="plus" className="h-4 w-4" /> Yeni reçete
        </Button>
      }
    >
      {error ? <Alert tone="error">{error}</Alert> : null}
      {recipes === null && !error ? (
        <p className="flex items-center gap-2 text-[14px] text-slate">
          <Spinner /> Yükleniyor
        </p>
      ) : null}
      {recipes && recipes.length === 0 ? (
        <p className="text-[14px] leading-6 text-slate">
          Henüz reçete yok. Örneğin “Meşe tabla 120 cm” için 0,5 adet kontrplak, 0,25 kutu vida ve 0,4 lt lake. Reçete tanımlı ürünlerde eksik stok için üretim emri otomatik açılabilir.
        </p>
      ) : null}
      {recipes && recipes.length > 0 ? (
        <ul className="divide-y divide-hairline">
          {recipes.map((recipe) => (
            <li key={recipe.product_id} className="flex items-center justify-between gap-3 py-3.5">
              <div className="min-w-0">
                <p className="truncate text-[14px] font-semibold">{recipe.name}</p>
                <p className="mt-0.5 text-[12.5px] text-slate">
                  <span className="font-mono">{recipe.sku}</span> · {recipe.materials} malzeme
                </p>
              </div>
              <Button size="sm" variant="quiet" onClick={() => setEditing({ id: recipe.product_id, label: recipe.name, meta: recipe.sku, unit: recipe.unit as Unit })}>
                Düzenle
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </Sheet>
  );
}

function RecipeEditor({ product: initial, onBack, onSaved }: { product: ProductOption | null; onBack: () => void; onSaved: () => void }) {
  const [product, setProduct] = useState<ProductOption | null>(initial);
  const [lines, setLines] = useState<Line[]>([blank()]);
  const [loading, setLoading] = useState(initial !== null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const search = useProductSearch();
  const productId = product?.id ?? null;

  useEffect(() => {
    if (!productId) return;
    let cancelled = false;
    fetchRecipe(productId)
      .then((recipe) => {
        if (cancelled) return;
        setLines(
          recipe.items.length
            ? recipe.items.map((item) => ({
                key: item.product_id,
                product: { id: item.product_id, label: item.name, meta: item.sku, unit: item.unit as Unit },
                quantity: item.quantity.replace(".", ","),
              }))
            : [blank()],
        );
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [productId]);

  async function save(items: Line[]) {
    if (!product) return setError("Reçetesi tanımlanacak ürünü seçin.");
    const filled = items.filter((line) => line.product);
    for (const line of filled) {
      const amount = parseQuantity(line.quantity);
      if (amount === null || Number(amount) <= 0) return setError(`${line.product?.label} için geçerli bir miktar girin.`);
    }
    setPending(true);
    setError("");
    try {
      await saveRecipe(
        product.id,
        filled.map((line) => ({ product_id: line.product?.id ?? "", quantity: parseQuantity(line.quantity) ?? "0" })),
      );
      onSaved();
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Reçete kaydedilemedi.");
      setPending(false);
    }
  }

  function update(key: string, patch: Partial<Line>) {
    setLines((current) => current.map((line) => (line.key === key ? { ...line, ...patch } : line)));
  }

  return (
    <Sheet
      wide
      title={initial ? `${initial.label} reçetesi` : "Yeni reçete"}
      description="Miktarlar bir birim ürün içindir. Adet, paket ve kutu birimindeki malzemeler iş emrinde yukarı yuvarlanır."
      busy={pending}
      onClose={onBack}
      footer={
        <>
          {initial ? (
            <Button variant="ghost" className="mr-auto text-error-text" onClick={() => void save([])} disabled={pending}>
              Reçeteyi kaldır
            </Button>
          ) : null}
          <Button variant="quiet" onClick={onBack} disabled={pending}>
            Geri
          </Button>
          <Button onClick={() => void save(lines)} pending={pending} pendingLabel="Kaydediliyor">
            Reçeteyi kaydet
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        {error ? <Alert tone="error">{error}</Alert> : null}
        {initial ? null : <Picker label="Üretilen ürün" value={product} onChange={(option) => setProduct(option as ProductOption | null)} search={search} create={quickProduct()} placeholder="Ürün adı veya SKU" />}
        {loading ? (
          <p className="flex items-center gap-2 text-[14px] text-slate">
            <Spinner /> Reçete yükleniyor
          </p>
        ) : (
          <section aria-labelledby="recipe-lines">
            <h3 id="recipe-lines" className="text-[12px] font-semibold uppercase tracking-[0.08em] text-slate">
              1 {product ? unitShort(product.unit) : "birim"} için malzemeler
            </h3>
            <ul className="mt-2 space-y-2">
              {lines.map((line, index) => (
                <li key={line.key} className="grid grid-cols-[minmax(0,1fr)_120px_36px] items-start gap-2">
                  <Picker
                    compact
                    label={`${index + 1}. malzeme`}
                    value={line.product}
                    onChange={(option) => update(line.key, { product: option as ProductOption | null })}
                    search={search} create={quickProduct()}
                    placeholder="Malzeme ara"
                  />
                  <span className="relative block">
                    <input
                      inputMode="decimal"
                      aria-label={`${index + 1}. malzeme miktarı`}
                      value={line.quantity}
                      placeholder="0"
                      onChange={(event) => update(line.key, { quantity: event.target.value })}
                      className={`h-10 w-full rounded-lg border border-mist bg-surface pl-3 ${line.product && unitShort(line.product.unit).length > 3 ? "pr-14" : "pr-10"} text-right text-[14px] tabular-nums outline-none hover:border-stone focus:border-violet`}
                    />
                    <span aria-hidden className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-[12px] text-slate">
                      {line.product ? unitShort(line.product.unit) : ""}
                    </span>
                  </span>
                  <button
                    type="button"
                    aria-label={`${index + 1}. malzemeyi kaldır`}
                    disabled={lines.length === 1}
                    onClick={() => setLines((current) => current.filter((item) => item.key !== line.key))}
                    className="grid h-10 w-9 place-items-center rounded-lg text-slate transition-colors hover:bg-error/[0.06] hover:text-error-text disabled:opacity-30"
                  >
                    <Icon name="trash" className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
            <button
              type="button"
              onClick={() => setLines((current) => [...current, blank()])}
              disabled={lines.length >= 50}
              className="mt-2 inline-flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-semibold text-violet hover:bg-violet/[0.06]"
            >
              <Icon name="plus" className="h-4 w-4" strokeWidth={2} />
              Malzeme ekle
            </button>
          </section>
        )}
      </div>
    </Sheet>
  );
}
