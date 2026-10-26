import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiRequestError } from "../../lib/http.ts";
import { fetchProducts, formatQuantity, parseQuantity, unitShort, wholeUnitMessage, wholeUnits, type Unit } from "../../lib/inventory.ts";
import { createProductionOrder, fetchRecipe, updateProductionOrder, type ProductionDetail, type ProductionPayload, type Recipe } from "../../lib/production.ts";
import { Alert, Button, TextArea } from "../forms/Controls.tsx";
import { quickProduct } from "../../lib/quickCreate.ts";
import { Picker, type PickerOption } from "../forms/Picker.tsx";
import { Icon } from "../ui/Icon.tsx";
import { Sheet } from "../ui/Sheet.tsx";

export type ProductOption = PickerOption & { unit: Unit };
type Line = { key: string; product: ProductOption | null; quantity: string };
type Errors = { output?: string; quantity?: string; lines: Record<string, string> };

const control =
  "h-11 w-full rounded-lg border bg-surface px-3 text-[15px] text-graphite outline-none hover:border-stone focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)]";

function blank(): Line {
  return { key: crypto.randomUUID(), product: null, quantity: "" };
}

function checkQuantity(value: string, unit: Unit | undefined): string | null {
  const parsed = parseQuantity(value);
  if (parsed === null || Number(parsed) <= 0) return "Geçerli bir miktar girin.";
  if (unit && wholeUnits.has(unit) && !Number.isInteger(Number(parsed))) return wholeUnitMessage(unit);
  return null;
}

function scaled(perUnit: string, quantity: string | null, unit: Unit): string {
  const amount = Number(perUnit) * Number(quantity ?? 0);
  const rounded = wholeUnits.has(unit) ? Math.ceil(amount - 1e-9) : Math.ceil(amount * 1000 - 1e-6) / 1000;
  return String(rounded).replace(".", ",");
}

export type ProductionPrefill = { product: ProductOption; quantity: string };

export function ProductionEditor({
  order,
  prefill = null,
  onClose,
  onSaved,
}: {
  order: ProductionDetail | null;
  prefill?: ProductionPrefill | null;
  onClose: () => void;
  onSaved: (order: ProductionDetail) => void;
}) {
  const [output, setOutput] = useState<ProductOption | null>(
    order ? { id: order.product_id, label: order.product_name, meta: order.product_sku, unit: order.unit as Unit } : (prefill?.product ?? null),
  );
  const [quantity, setQuantity] = useState(order ? order.quantity.replace(".", ",") : (prefill?.quantity.replace(".", ",") ?? ""));
  const [recipe, setRecipe] = useState<Recipe | null>(null);
  const [fromRecipe, setFromRecipe] = useState(order === null);
  const [plannedDate, setPlannedDate] = useState(order?.planned_date ?? "");
  const [note, setNote] = useState(order?.note ?? "");
  const [lines, setLines] = useState<Line[]>(
    order
      ? order.materials.map((item) => ({
          key: item.product_id,
          product: { id: item.product_id, label: item.name, meta: item.sku, unit: item.unit as Unit },
          quantity: item.quantity.replace(".", ","),
        }))
      : [blank()],
  );
  const [errors, setErrors] = useState<Errors>({ lines: {} });
  const [formError, setFormError] = useState("");
  const [pending, setPending] = useState(false);

  const searchProducts = useCallback(async (q: string) => {
    const page = await fetchProducts({ q, pageSize: 8, sort: "name" });
    return page.items.map((item) => ({
      id: item.id,
      label: item.name,
      meta: `${item.sku} · stok ${formatQuantity(item.stock_quantity)} ${unitShort(item.unit)}`,
      unit: item.unit,
    }));
  }, []);

  const outputId = output?.id ?? null;
  useEffect(() => {
    if (!outputId) return;
    let cancelled = false;
    fetchRecipe(outputId)
      .then((next) => {
        if (!cancelled) setRecipe(next.items.length > 0 ? next : null);
      })
      .catch(() => {
        if (!cancelled) setRecipe(null);
      });
    return () => {
      cancelled = true;
    };
  }, [outputId]);

  const activeRecipe = recipe && recipe.product_id === outputId ? recipe : null;
  const recipeLines = (source: Recipe, amount: string): Line[] =>
    source.items
      .filter((item) => !item.deleted)
      .map((item) => ({
        key: `recipe-${item.product_id}`,
        product: { id: item.product_id, label: item.name, meta: item.sku, unit: item.unit as Unit },
        quantity: scaled(item.quantity, parseQuantity(amount), item.unit as Unit),
      }));
  const shownLines = fromRecipe && activeRecipe ? recipeLines(activeRecipe, quantity) : lines;

  function updateLine(key: string, patch: Partial<Line>) {
    const base = fromRecipe && activeRecipe ? recipeLines(activeRecipe, quantity) : lines;
    setFromRecipe(false);
    setLines(base.map((line) => (line.key === key ? { ...line, ...patch } : line)));
    setErrors((current) => ({ ...current, lines: { ...current.lines, [key]: "" } }));
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    const next: Errors = { lines: {} };
    if (!output) next.output = "Üretilecek ürünü seçin.";
    const quantityError = checkQuantity(quantity, output?.unit);
    if (quantityError) next.quantity = quantityError;
    const used = new Set<string>();
    const lines = shownLines;
    for (const line of lines) {
      if (!line.product) next.lines[line.key] = "Malzeme seçin.";
      else if (line.product.id === output?.id) next.lines[line.key] = "Üretilen ürün kendi malzemesi olamaz.";
      else if (used.has(line.product.id)) next.lines[line.key] = "Bu malzeme zaten ekli.";
      else next.lines[line.key] = checkQuantity(line.quantity, line.product.unit) ?? "";
      if (line.product) used.add(line.product.id);
    }
    setErrors(next);
    if (next.output || next.quantity || Object.values(next.lines).some(Boolean) || !output) return;

    const payload: ProductionPayload = {
      product_id: output.id,
      quantity: parseQuantity(quantity) ?? "0",
      planned_date: plannedDate || null,
      note,
      materials: lines.map((line) => ({ product_id: line.product?.id ?? "", quantity: parseQuantity(line.quantity) ?? "0" })),
    };
    setPending(true);
    try {
      onSaved(order ? await updateProductionOrder(order.id, payload) : await createProductionOrder(payload));
    } catch (error) {
      setFormError(error instanceof ApiRequestError ? error.message : "İş emri kaydedilemedi.");
      setPending(false);
    }
  }

  return (
    <Sheet
      wide
      title={order ? `${order.code} iş emrini düzenle` : "Yeni iş emri"}
      description="Planlanan iş emri stoğa dokunmaz. Tamamlandığında malzemeler stoktan düşülür, ürün stoğa girer."
      busy={pending}
      onClose={onClose}
      onSubmit={(event) => void onSubmit(event)}
      initialFocus={order ? "#production-quantity" : '[name="output"]'}
      footer={
        <>
          <Button type="button" variant="quiet" onClick={onClose} disabled={pending}>
            Vazgeç
          </Button>
          <Button type="submit" pending={pending} pendingLabel="Kaydediliyor">
            {order ? "Değişiklikleri kaydet" : "İş emrini oluştur"}
          </Button>
        </>
      }
    >
      <div className="space-y-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-[minmax(0,1fr)_150px_160px]">
          <Picker
            label="Üretilecek ürün"
            name="output"
            value={output}
            onChange={(option) => {
              setOutput(option as ProductOption | null);
              if (shownLines.every((line) => !line.product)) setFromRecipe(true);
              setErrors((current) => ({ ...current, output: undefined }));
            }}
            search={searchProducts}
            create={quickProduct()}
            placeholder="Ürün adı veya SKU"
            emptyText="Eşleşen ürün yok. Önce Stok ve Depo modülünden ekleyin."
            error={errors.output}
          />
          <div>
            <label htmlFor="production-quantity" className="text-[13px] font-medium text-graphite">
              Miktar{output ? ` (${unitShort(output.unit)})` : ""}
            </label>
            <input
              id="production-quantity"
              inputMode="decimal"
              value={quantity}
              aria-invalid={errors.quantity ? true : undefined}
              onChange={(event) => {
                setQuantity(event.target.value);
                setErrors((current) => ({ ...current, quantity: undefined }));
              }}
              className={`${control} mt-1.5 text-right tabular-nums ${errors.quantity ? "border-error/70" : "border-mist"}`}
            />
            {errors.quantity ? <p className="mt-1.5 text-[12px] text-error-text">{errors.quantity}</p> : null}
          </div>
          <div>
            <label htmlFor="production-date" className="text-[13px] font-medium text-graphite">
              Plan tarihi
            </label>
            <input id="production-date" type="date" value={plannedDate} onChange={(event) => setPlannedDate(event.target.value)} className={`${control} mt-1.5 border-mist`} />
          </div>
        </div>

        <section aria-labelledby="materials-title">
          <div className="flex items-center justify-between">
            <h3 id="materials-title" className="text-[14px] font-semibold">
              Kullanılacak malzemeler
            </h3>
            <span className="text-[12px] text-slate">Toplam miktarları girin</span>
          </div>
          {activeRecipe ? (
            <p className="mt-1.5 flex flex-wrap items-center gap-x-2 text-[12.5px] text-slate">
              {fromRecipe ? (
                <>Malzemeler ürün reçetesinden miktara göre hesaplanıyor.</>
              ) : (
                <>
                  Malzemeleri elle değiştirdiniz.
                  <button type="button" onClick={() => setFromRecipe(true)} className="font-semibold text-violet hover:underline">
                    Reçeteden yeniden hesapla
                  </button>
                </>
              )}
            </p>
          ) : null}
          <ul className="mt-2 space-y-2">
            {shownLines.map((line, index) => (
              <li key={line.key} className="grid grid-cols-[minmax(0,1fr)_110px_36px] items-start gap-2">
                <Picker
                  compact
                  label={`${index + 1}. malzeme`}
                  value={line.product}
                  onChange={(option) => updateLine(line.key, { product: option as ProductOption | null })}
                  search={searchProducts}
            create={quickProduct()}
                  placeholder="Malzeme ara"
                  emptyText="Eşleşen ürün yok."
                />
                <label className="block">
                  <span className="sr-only">{`${index + 1}. malzeme miktarı${line.product ? ` (${unitShort(line.product.unit)})` : ""}`}</span>
                  <span className="relative block">
                    <input
                      inputMode="decimal"
                      value={line.quantity}
                      placeholder="0"
                      aria-invalid={errors.lines[line.key] ? true : undefined}
                      onChange={(event) => updateLine(line.key, { quantity: event.target.value })}
                      className={`h-10 w-full rounded-lg border bg-surface pl-3 ${line.product && unitShort(line.product.unit).length > 3 ? "pr-14" : "pr-10"} text-right text-[14px] tabular-nums outline-none focus:border-violet ${
                        errors.lines[line.key] ? "border-error/70" : "border-mist hover:border-stone"
                      }`}
                    />
                    <span aria-hidden className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-[12px] text-slate">
                      {line.product ? unitShort(line.product.unit) : ""}
                    </span>
                  </span>
                </label>
                <button
                  type="button"
                  aria-label={`${index + 1}. malzemeyi kaldır`}
                  disabled={shownLines.length === 1}
                  onClick={() => {
                    setLines(shownLines.filter((item) => item.key !== line.key));
                    setFromRecipe(false);
                  }}
                  className="grid h-10 w-9 place-items-center rounded-lg text-slate transition-colors hover:bg-error/[0.06] hover:text-error-text disabled:opacity-30"
                >
                  <Icon name="trash" className="h-4 w-4" />
                </button>
                {errors.lines[line.key] ? <p className="col-span-3 -mt-1 text-[12px] text-error-text">{errors.lines[line.key]}</p> : null}
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={() => {
              setLines([...shownLines, blank()]);
              setFromRecipe(false);
            }}
            disabled={shownLines.length >= 50}
            className="mt-2 inline-flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-semibold text-violet hover:bg-violet/[0.06]"
          >
            <Icon name="plus" className="h-4 w-4" strokeWidth={2} />
            Malzeme ekle
          </button>
        </section>

        <TextArea label="Not" name="note" rows={3} maxLength={1000} value={note} onValue={setNote} />
        {formError ? <Alert tone="error">{formError}</Alert> : null}
      </div>
    </Sheet>
  );
}
