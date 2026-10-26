import { useState, type FormEvent } from "react";
import { ApiRequestError } from "../../lib/http.ts";
import {
  createProduct,
  parseQuantity,
  units,
  updateProduct,
  wholeUnitMessage,
  wholeUnits,
  type Product,
  type ProductDraft,
  type Unit,
} from "../../lib/inventory.ts";
import { Alert, Button, Field, TextArea } from "../forms/Controls.tsx";
import { Sheet } from "../ui/Sheet.tsx";

type Form = { sku: string; name: string; unit: Unit; min_stock: string; critical_stock: string; initial_stock: string; description: string };
type Errors = Partial<Record<keyof Form, string>>;

const order: (keyof Form)[] = ["sku", "name", "unit", "min_stock", "critical_stock", "initial_stock", "description"];

function validate(form: Form, creating: boolean): Errors {
  const errors: Errors = {};
  if (!form.sku.trim()) errors.sku = "Stok kodu girin.";
  else if (!/^[A-Za-z0-9._/-]+$/.test(form.sku.trim())) errors.sku = "Stok kodu yalnızca harf, rakam ve . _ - / içerebilir.";
  if (form.name.trim().length < 2) errors.name = "Ürün adı en az 2 karakter olmalı.";
  const amounts: (keyof Form)[] = creating ? ["min_stock", "initial_stock"] : ["min_stock"];
  for (const key of amounts) {
    const value = form[key].trim() === "" ? "0" : parseQuantity(form[key]);
    if (value === null) errors[key] = "Geçerli bir miktar girin. Örnek: 12 veya 2,5";
    else if (wholeUnits.has(form.unit) && !Number.isInteger(Number(value))) errors[key] = wholeUnitMessage(form.unit);
  }
  if (form.critical_stock.trim()) {
    const critical = parseQuantity(form.critical_stock);
    const minimum = Number(parseQuantity(form.min_stock || "0") ?? 0);
    if (critical === null) errors.critical_stock = "Geçerli bir miktar girin. Örnek: 3 veya 1,5";
    else if (wholeUnits.has(form.unit) && !Number.isInteger(Number(critical))) errors.critical_stock = wholeUnitMessage(form.unit);
    else if (minimum > 0 && Number(critical) > minimum) errors.critical_stock = "Kritik stok, minimum stoktan büyük olamaz.";
  }
  return errors;
}

export function ProductEditor({ product, onClose, onSaved }: { product: Product | null; onClose: () => void; onSaved: (product: Product, created: boolean) => void }) {
  const creating = product === null;
  const [form, setForm] = useState<Form>({
    sku: product?.sku ?? "",
    name: product?.name ?? "",
    unit: product?.unit ?? "adet",
    min_stock: product ? product.min_stock.replace(".", ",") : "",
    critical_stock: product?.critical_stock ? product.critical_stock.replace(".", ",") : "",
    initial_stock: "",
    description: product?.description ?? "",
  });
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState("");
  const [pending, setPending] = useState(false);

  function update(key: keyof Form, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
    if (errors[key]) setErrors((current) => ({ ...current, [key]: undefined }));
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const element = event.currentTarget;
    const focus = (next: Errors) => {
      const first = order.find((key) => next[key]);
      if (first) element.querySelector<HTMLElement>(`[name="${first}"]`)?.focus();
    };
    setFormError("");
    const local = validate(form, creating);
    setErrors(local);
    if (Object.keys(local).length > 0) {
      focus(local);
      return;
    }
    const draft: ProductDraft = {
      sku: form.sku.trim(),
      name: form.name,
      unit: form.unit,
      min_stock: parseQuantity(form.min_stock || "0") ?? "0",
      critical_stock: form.critical_stock.trim() ? parseQuantity(form.critical_stock) : null,
      description: form.description,
      ...(creating ? { initial_stock: parseQuantity(form.initial_stock || "0") ?? "0" } : {}),
    };
    setPending(true);
    try {
      const saved = product ? await updateProduct(product.id, draft) : await createProduct(draft);
      onSaved(saved, creating);
    } catch (error) {
      if (error instanceof ApiRequestError && error.status === 409) {
        setErrors({ sku: error.message });
        focus({ sku: error.message });
      } else if (error instanceof ApiRequestError && Object.keys(error.fields).length > 0) {
        setErrors(error.fields as Errors);
        focus(error.fields as Errors);
      } else {
        setFormError(error instanceof ApiRequestError ? error.message : "Ürün kaydedilemedi.");
      }
      setPending(false);
    }
  }

  return (
    <Sheet
      title={creating ? "Yeni ürün" : "Ürünü düzenle"}
      description={creating ? "Stok kodu, ad ve birim zorunludur." : `${product.sku} · ${product.name}`}
      busy={pending}
      onClose={onClose}
      onSubmit={(event) => void onSubmit(event)}
      initialFocus={creating ? '[name="sku"]' : '[name="name"]'}
      footer={
        <>
          <Button type="button" variant="quiet" onClick={onClose} disabled={pending}>
            Vazgeç
          </Button>
          <Button type="submit" pending={pending} pendingLabel="Kaydediliyor">
            {creating ? "Ürünü ekle" : "Değişiklikleri kaydet"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <Field label="Stok kodu (SKU)" name="sku" autoComplete="off" placeholder="MT-001" value={form.sku} error={errors.sku} onValue={(value) => update("sku", value)} />
          <div>
            <label htmlFor="product-unit" className="text-[13px] font-medium text-graphite">
              Birim
            </label>
            <select
              id="product-unit"
              name="unit"
              value={form.unit}
              onChange={(event) => update("unit", event.target.value)}
              className="mt-1.5 h-11 w-full rounded-lg border border-mist bg-surface px-3 text-[15px] text-graphite outline-none hover:border-stone focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)]"
            >
              {units.map((unit) => (
                <option key={unit.value} value={unit.value}>
                  {unit.label} ({unit.short})
                </option>
              ))}
            </select>
          </div>
        </div>
        <Field label="Ürün adı" name="name" autoComplete="off" value={form.name} error={errors.name} onValue={(value) => update("name", value)} />
        <div className={`grid gap-4 ${creating ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}>
          <Field
            label="Minimum stok"
            name="min_stock"
            inputMode="decimal"
            autoComplete="off"
            placeholder="0"
            value={form.min_stock}
            error={errors.min_stock}
            hint="Altına düşünce uyarı verilir."
            onValue={(value) => update("min_stock", value)}
          />
          <Field
            label="Kritik stok (isteğe bağlı)"
            name="critical_stock"
            inputMode="decimal"
            autoComplete="off"
            placeholder={Number(parseQuantity(form.min_stock || "0") ?? 0) > 0 ? `Boşsa ${String(Number(parseQuantity(form.min_stock) ?? 0) / 2).replace(".", ",")}` : "Boş"}
            value={form.critical_stock}
            error={errors.critical_stock}
            hint="Bu seviyeye inince sahip ve yöneticilere acil uyarı gider. Boşsa minimumun yarısı."
            onValue={(value) => update("critical_stock", value)}
          />
          {creating ? (
            <Field
              label="Açılış stoku"
              name="initial_stock"
              inputMode="decimal"
              autoComplete="off"
              placeholder="0"
              value={form.initial_stock}
              error={errors.initial_stock}
              hint="Giriş hareketi olarak kaydedilir."
              onValue={(value) => update("initial_stock", value)}
            />
          ) : null}
        </div>
        <TextArea label="Açıklama" name="description" maxLength={1000} value={form.description} onValue={(value) => update("description", value)} />
        {!creating ? <p className="text-[13px] text-slate">Stok miktarı bu formdan değişmez; giriş, çıkış veya sayım için “Stok hareketi” panelini kullanın.</p> : null}
        {formError ? <Alert tone="error">{formError}</Alert> : null}
      </div>
    </Sheet>
  );
}
