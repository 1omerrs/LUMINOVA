import { useCallback, useState, type FormEvent } from "react";
import { fetchCustomers } from "../../lib/customers.ts";
import { ApiRequestError } from "../../lib/http.ts";
import { fetchProducts, formatQuantity, parseQuantity, unitShort, wholeUnitMessage, wholeUnits, type Unit } from "../../lib/inventory.ts";
import {
  createOrder,
  currencies,
  formatMoney,
  parseMoney,
  updateOrder,
  vatRates,
  type Currency,
  type OrderDetail,
  type OrderLine,
  type OrderPayload,
  type VatRate,
} from "../../lib/sales.ts";
import { Alert, Button, TextArea } from "../forms/Controls.tsx";
import { quickCustomer, quickProduct } from "../../lib/quickCreate.ts";
import { Picker, type PickerOption } from "../forms/Picker.tsx";
import { Icon } from "../ui/Icon.tsx";
import { Sheet } from "../ui/Sheet.tsx";

type Line = {
  key: string;
  product: (PickerOption & { unit: Unit }) | null;
  description: string;
  quantity: string;
  unitPrice: string;
  vatRate: VatRate;
  discount: string;
};
type LineErrors = Partial<Record<"item" | "quantity" | "unitPrice" | "discount", string>>;

const today = () => new Date().toLocaleDateString("sv-SE");
const selectClass =
  "h-10 w-full rounded-lg border border-mist bg-surface px-2.5 text-[14px] text-graphite outline-none hover:border-stone focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)]";
const inputClass = (error?: string) =>
  `h-10 w-full rounded-lg border bg-surface px-3 text-right text-[14px] tabular-nums outline-none focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)] ${
    error ? "border-error/70" : "border-mist hover:border-stone"
  }`;

function blankLine(): Line {
  return { key: crypto.randomUUID(), product: null, description: "", quantity: "1", unitPrice: "", vatRate: 20, discount: "" };
}

function round(value: number): number {
  return Math.round(value * 100 + Number.EPSILON) / 100;
}

function parseRate(input: string): string | null {
  const cleaned = input.trim().replace("%", "").replace(",", ".");
  if (cleaned === "") return "0";
  if (!/^\d{1,3}(\.\d{1,2})?$/.test(cleaned) || Number(cleaned) > 100) return null;
  return cleaned;
}

function lineAmounts(line: Line) {
  const quantity = Number(parseQuantity(line.quantity) ?? 0);
  const price = Number(parseMoney(line.unitPrice) ?? 0);
  const gross = round(quantity * price);
  const discount = round((gross * Number(parseRate(line.discount) ?? 0)) / 100);
  const subtotal = gross - discount;
  const vat = round((subtotal * line.vatRate) / 100);
  return { discount, subtotal, vat, total: subtotal + vat };
}

export type EditableDocument = {
  id: string;
  code: string;
  customer_id: string;
  customer_name: string;
  currency: Currency;
  date: string;
  valid_until?: string | null;
  note: string | null;
  items: OrderLine[];
};

export type LinePayload = Omit<OrderPayload, "order_date"> & { date: string; valid_until: string | null };

type Labels = { title: string; description: string; date: string; save: string; failed: string };

export function OrderEditor({
  order,
  initialCustomer = null,
  onClose,
  onSaved,
}: {
  order: OrderDetail | null;
  initialCustomer?: PickerOption | null;
  onClose: () => void;
  onSaved: (order: OrderDetail) => void;
}) {
  return (
    <LineItemsEditor
      document={order ? { ...order, date: order.order_date } : null}
      initialCustomer={initialCustomer}
      labels={{
        title: order ? `${order.code} siparişini düzenle` : "Yeni sipariş",
        description: "Sipariş taslak olarak kaydedilir; onaylayıp teslim ettiğinizde stoktan düşülür.",
        date: "Sipariş tarihi",
        save: order ? "Değişiklikleri kaydet" : "Taslağı kaydet",
        failed: "Sipariş kaydedilemedi.",
      }}
      productsEnabled
      onClose={onClose}
      save={async ({ date, valid_until: _ignored, ...rest }) => {
        const payload: OrderPayload = { ...rest, order_date: date };
        onSaved(order ? await updateOrder(order.id, payload) : await createOrder(payload));
      }}
    />
  );
}

export function LineItemsEditor({
  document,
  labels,
  productsEnabled,
  withValidity = false,
  initialCustomer = null,
  onClose,
  save,
}: {
  document: EditableDocument | null;
  labels: Labels;
  productsEnabled: boolean;
  withValidity?: boolean;
  initialCustomer?: PickerOption | null;
  onClose: () => void;
  save: (payload: LinePayload) => Promise<void>;
}) {
  const order = document;
  const [customer, setCustomer] = useState<PickerOption | null>(order ? { id: order.customer_id, label: order.customer_name } : initialCustomer);
  const [orderDate, setOrderDate] = useState(order?.date ?? today());
  const [validUntil, setValidUntil] = useState(order?.valid_until ?? "");
  const [currency, setCurrency] = useState<Currency>(order?.currency ?? "TRY");
  const [note, setNote] = useState(order?.note ?? "");
  const [lines, setLines] = useState<Line[]>(
    order
      ? order.items.map((item) => ({
          key: item.id,
          product: item.product_id ? { id: item.product_id, label: item.description, meta: item.product_sku ?? undefined, unit: (item.product_unit ?? "adet") as Unit } : null,
          description: item.product_id ? "" : item.description,
          quantity: item.quantity.replace(".", ","),
          unitPrice: item.unit_price.replace(".", ","),
          vatRate: item.vat_rate,
          discount: item.discount_rate && item.discount_rate !== "0" ? item.discount_rate.replace(".", ",") : "",
        }))
      : [blankLine()],
  );
  const [customerError, setCustomerError] = useState("");
  const [lineErrors, setLineErrors] = useState<Record<string, LineErrors>>({});
  const [formError, setFormError] = useState("");
  const [pending, setPending] = useState(false);

  const searchCustomers = useCallback(async (q: string) => {
    const page = await fetchCustomers({ q, pageSize: 8, sort: "name" });
    return page.items.map((item) => ({ id: item.id, label: item.name, meta: item.email ?? item.phone ?? undefined }));
  }, []);

  const searchProducts = useCallback(async (q: string) => {
    const page = await fetchProducts({ q, pageSize: 8, sort: "name" });
    return page.items.map((item) => ({
      id: item.id,
      label: item.name,
      meta:
        item.reserved && item.reserved !== "0"
          ? `${item.sku} · kullanılabilir ${formatQuantity(item.available)} / stok ${formatQuantity(item.stock_quantity)} ${unitShort(item.unit)}`
          : `${item.sku} · stok ${formatQuantity(item.stock_quantity)} ${unitShort(item.unit)}`,
      unit: item.unit,
    }));
  }, []);

  function updateLine(key: string, patch: Partial<Line>) {
    setLines((current) => current.map((line) => (line.key === key ? { ...line, ...patch } : line)));
    setLineErrors((current) => ({ ...current, [key]: {} }));
  }

  const totals = lines.reduce(
    (sum, line) => {
      const amounts = lineAmounts(line);
      return { subtotal: sum.subtotal + amounts.subtotal, vat: sum.vat + amounts.vat, discount: sum.discount + amounts.discount };
    },
    { subtotal: 0, vat: 0, discount: 0 },
  );

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    let valid = true;
    if (!customer) {
      setCustomerError("Müşteri seçin.");
      valid = false;
    }
    const errors: Record<string, LineErrors> = {};
    for (const line of lines) {
      const current: LineErrors = {};
      if (!line.product && !line.description.trim()) current.item = "Ürün seçin veya açıklama yazın.";
      const quantity = parseQuantity(line.quantity);
      if (quantity === null || Number(quantity) <= 0) current.quantity = "Geçerli miktar girin.";
      else if (line.product && wholeUnits.has(line.product.unit) && !Number.isInteger(Number(quantity))) current.quantity = wholeUnitMessage(line.product.unit);
      if (parseMoney(line.unitPrice) === null) current.unitPrice = "Geçerli fiyat girin.";
      if (parseRate(line.discount) === null) current.discount = "İskonto 0 ile 100 arasında olmalı.";
      if (Object.keys(current).length > 0) {
        errors[line.key] = current;
        valid = false;
      }
    }
    if (withValidity && validUntil && validUntil < orderDate) {
      setFormError("Geçerlilik tarihi teklif tarihinden önce olamaz.");
      valid = false;
    }
    setLineErrors(errors);
    if (!valid || !customer) return;

    const payload: LinePayload = {
      customer_id: customer.id,
      currency,
      date: orderDate,
      valid_until: withValidity && validUntil ? validUntil : null,
      note,
      items: lines.map((line) => ({
        product_id: line.product?.id ?? null,
        description: line.product ? "" : line.description,
        quantity: parseQuantity(line.quantity) ?? "0",
        unit_price: parseMoney(line.unitPrice) ?? "0",
        vat_rate: line.vatRate,
        discount_rate: parseRate(line.discount) ?? "0",
      })),
    };
    setPending(true);
    try {
      await save(payload);
    } catch (error) {
      setFormError(error instanceof ApiRequestError ? error.message : labels.failed);
      setPending(false);
    }
  }

  return (
    <Sheet
      wide
      title={labels.title}
      description={labels.description}
      busy={pending}
      onClose={onClose}
      onSubmit={(event) => void onSubmit(event)}
      initialFocus={order ? undefined : '[name="customer"]'}
      footer={
        <>
          <Button type="button" variant="quiet" onClick={onClose} disabled={pending}>
            Vazgeç
          </Button>
          <Button type="submit" pending={pending} pendingLabel="Kaydediliyor">
            {labels.save}
          </Button>
        </>
      }
    >
      <div className="space-y-6">
        <div className={`grid gap-4 ${withValidity ? "sm:grid-cols-[minmax(0,1fr)_150px_150px_110px]" : "sm:grid-cols-[minmax(0,1fr)_160px_120px]"}`}>
          <Picker
            label="Müşteri"
            name="customer"
            value={customer}
            onChange={(option) => {
              setCustomer(option);
              setCustomerError("");
            }}
            search={searchCustomers}
            create={quickCustomer}
            placeholder="Müşteri adıyla arayın"
            emptyText="Eşleşen müşteri yok. Önce Müşteri ve Teklifler modülünden ekleyin."
            error={customerError}
          />
          <div>
            <label htmlFor="order-date" className="text-[13px] font-medium text-graphite">
              {labels.date}
            </label>
            <input id="order-date" type="date" value={orderDate} onChange={(event) => setOrderDate(event.target.value)} className={`${selectClass} mt-1.5 h-11`} />
          </div>
          {withValidity ? (
            <div>
              <label htmlFor="valid-until" className="text-[13px] font-medium text-graphite">
                Geçerlilik tarihi
              </label>
              <input id="valid-until" type="date" value={validUntil} onChange={(event) => setValidUntil(event.target.value)} className={`${selectClass} mt-1.5 h-11`} />
            </div>
          ) : null}
          <div>
            <label htmlFor="order-currency" className="text-[13px] font-medium text-graphite">
              Para birimi
            </label>
            <select id="order-currency" value={currency} onChange={(event) => setCurrency(event.target.value as Currency)} className={`${selectClass} mt-1.5 h-11`}>
              {currencies.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
        </div>

        <section aria-labelledby="lines-title">
          <div className="flex items-center justify-between">
            <h3 id="lines-title" className="text-[14px] font-semibold">
              Satırlar
            </h3>
            <span className="text-[12px] text-slate">{lines.length} satır</span>
          </div>
          <div className="mt-2 hidden grid-cols-[minmax(0,1fr)_80px_104px_64px_78px_100px_32px] gap-2 px-1 text-[12px] text-slate md:grid">
            <span>Ürün veya açıklama</span>
            <span className="text-right">Miktar</span>
            <span className="text-right">Birim fiyat</span>
            <span className="text-right">İsk. %</span>
            <span>KDV</span>
            <span className="text-right">Tutar</span>
            <span />
          </div>
          <ul className="mt-1 space-y-2">
            {lines.map((line, index) => {
              const errors = lineErrors[line.key] ?? {};
              const amounts = lineAmounts(line);
              return (
                <li key={line.key} className="rounded-xl border border-mist/70 p-3 md:border-0 md:p-1">
                  <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_80px_104px_64px_78px_100px_32px] md:items-start">
                    <div className="space-y-1.5">
                      {productsEnabled ? (
                        <Picker
                          compact
                          label={`${index + 1}. satır ürünü`}
                          value={line.product}
                          onChange={(option) => updateLine(line.key, { product: option as Line["product"], description: "" })}
                          search={searchProducts}
                          create={quickProduct()}
                          placeholder="Ürün ara"
                          emptyText="Eşleşen ürün yok. Aşağıya açıklama yazabilirsiniz."
                        />
                      ) : null}
                      {line.product ? null : (
                        <input
                          aria-label={`${index + 1}. satır açıklaması`}
                          value={line.description}
                          onChange={(event) => updateLine(line.key, { description: event.target.value })}
                          placeholder={productsEnabled ? "veya hizmet/açıklama yazın" : "Ürün veya hizmet açıklaması"}
                          className="h-9 w-full rounded-lg border border-dashed border-mist bg-surface px-3 text-[13px] outline-none placeholder:text-slate/70 focus:border-violet"
                        />
                      )}
                      {errors.item ? <p className="text-[12px] text-error-text">{errors.item}</p> : null}
                    </div>
                    <div>
                      <label className="block text-[12px] text-slate">
                        <span className="md:sr-only">Miktar{line.product ? ` (${unitShort(line.product.unit)})` : ""}</span>
                        <input
                          inputMode="decimal"
                          aria-label={`${index + 1}. satır miktarı${line.product ? ` (${unitShort(line.product.unit)})` : ""}`}
                          aria-invalid={errors.quantity ? true : undefined}
                          value={line.quantity}
                          onChange={(event) => updateLine(line.key, { quantity: event.target.value })}
                          className={`${inputClass(errors.quantity)} mt-1 text-graphite md:mt-0`}
                        />
                      </label>
                      {errors.quantity ? <p className="mt-1 text-[12px] text-error-text">{errors.quantity}</p> : null}
                    </div>
                    <div>
                      <label className="block text-[12px] text-slate">
                        <span className="md:sr-only">Birim fiyat</span>
                        <input
                          inputMode="decimal"
                          placeholder="0,00"
                          aria-label={`${index + 1}. satır birim fiyatı`}
                          aria-invalid={errors.unitPrice ? true : undefined}
                          value={line.unitPrice}
                          onChange={(event) => updateLine(line.key, { unitPrice: event.target.value })}
                          className={`${inputClass(errors.unitPrice)} mt-1 text-graphite md:mt-0`}
                        />
                      </label>
                      {errors.unitPrice ? <p className="mt-1 text-[12px] text-error-text">{errors.unitPrice}</p> : null}
                    </div>
                    <div>
                      <label className="block text-[12px] text-slate">
                        <span className="md:sr-only">İskonto %</span>
                        <input
                          inputMode="decimal"
                          placeholder="0"
                          aria-label={`${index + 1}. satır iskonto yüzdesi`}
                          aria-invalid={errors.discount ? true : undefined}
                          value={line.discount}
                          onChange={(event) => updateLine(line.key, { discount: event.target.value })}
                          className={`${inputClass(errors.discount)} mt-1 text-graphite md:mt-0`}
                        />
                      </label>
                      {errors.discount ? <p className="mt-1 text-[12px] text-error-text">{errors.discount}</p> : null}
                    </div>
                    <label className="block text-[12px] text-slate">
                      <span className="md:sr-only">KDV</span>
                      <select
                        aria-label={`${index + 1}. satır KDV oranı`}
                        value={line.vatRate}
                        onChange={(event) => updateLine(line.key, { vatRate: Number(event.target.value) as VatRate })}
                        className={`${selectClass} mt-1 md:mt-0`}
                      >
                        {vatRates.map((rate) => (
                          <option key={rate} value={rate}>
                            %{rate}
                          </option>
                        ))}
                      </select>
                    </label>
                    <p className="flex h-10 items-center justify-between text-[14px] font-semibold tabular-nums md:justify-end">
                      <span className="text-[12px] font-normal text-slate md:sr-only">Tutar (KDV dahil)</span>
                      {formatMoney(amounts.total, currency)}
                    </p>
                    <button
                      type="button"
                      aria-label={`${index + 1}. satırı kaldır`}
                      disabled={lines.length === 1}
                      onClick={() => setLines((current) => current.filter((item) => item.key !== line.key))}
                      className="grid h-10 w-8 place-items-center rounded-lg text-slate transition-colors hover:bg-error/[0.06] hover:text-error-text disabled:opacity-30"
                    >
                      <Icon name="trash" className="h-4 w-4" />
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
          <button
            type="button"
            onClick={() => setLines((current) => [...current, blankLine()])}
            disabled={lines.length >= 100}
            className="mt-2 inline-flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-semibold text-violet hover:bg-violet/[0.06]"
          >
            <Icon name="plus" className="h-4 w-4" strokeWidth={2} />
            Satır ekle
          </button>
        </section>

        <div className="grid gap-6 sm:grid-cols-[minmax(0,1fr)_260px]">
          <TextArea label="Not" name="note" rows={3} maxLength={1000} value={note} onValue={setNote} />
          <dl className="space-y-2 self-end rounded-2xl bg-cloud px-4 py-4 text-[14px]">
            {totals.discount > 0 ? (
              <div className="flex justify-between">
                <dt className="text-slate">İskonto</dt>
                <dd className="tabular-nums text-success-text">−{formatMoney(totals.discount, currency)}</dd>
              </div>
            ) : null}
            <div className="flex justify-between">
              <dt className="text-slate">Ara toplam</dt>
              <dd className="tabular-nums">{formatMoney(totals.subtotal, currency)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate">KDV</dt>
              <dd className="tabular-nums">{formatMoney(totals.vat, currency)}</dd>
            </div>
            <div className="flex justify-between border-t border-mist pt-2 text-[16px] font-semibold">
              <dt>Genel toplam</dt>
              <dd className="tabular-nums">{formatMoney(totals.subtotal + totals.vat, currency)}</dd>
            </div>
          </dl>
        </div>
        {formError ? <Alert tone="error">{formError}</Alert> : null}
      </div>
    </Sheet>
  );
}
