import { useCallback, useEffect, useState, type FormEvent } from "react";
import { fetchCustomers } from "../../lib/customers.ts";
import { createRecord, fetchCategories, kindLabels, updateRecord, type Categories, type FinanceRecord, type RecordKind, type RecordPayload } from "../../lib/finance.ts";
import { ApiRequestError } from "../../lib/http.ts";
import { currencies, parseMoney, type Currency } from "../../lib/sales.ts";
import { Alert, Button, Field, TextArea } from "../forms/Controls.tsx";
import { quickCustomer } from "../../lib/quickCreate.ts";
import { Picker, type PickerOption } from "../forms/Picker.tsx";
import { Sheet } from "../ui/Sheet.tsx";

type Errors = Partial<Record<"description" | "amount" | "category", string>>;
export type RecordPrefill = Partial<RecordPayload> & { customerName?: string; orderCode?: string };

const control =
  "mt-1.5 h-11 w-full rounded-lg border border-mist bg-surface px-3 text-[15px] text-graphite outline-none hover:border-stone focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)]";

export function RecordEditor({
  record,
  prefill,
  customersOn,
  today,
  onClose,
  onSaved,
}: {
  record: FinanceRecord | null;
  prefill?: RecordPrefill;
  customersOn: boolean;
  today: string;
  onClose: () => void;
  onSaved: (record: FinanceRecord, created: boolean) => void;
}) {
  const [categories, setCategories] = useState<Categories | null>(null);
  const [draft, setDraft] = useState<RecordPayload>(() => ({
    kind: record?.kind ?? prefill?.kind ?? "income",
    category: record?.category ?? prefill?.category ?? "",
    description: record?.description ?? prefill?.description ?? "",
    counterparty: record?.counterparty ?? prefill?.counterparty ?? "",
    customer_id: record?.customer_id ?? prefill?.customer_id ?? null,
    order_id: record?.order_id ?? prefill?.order_id ?? null,
    amount: (record?.amount ?? prefill?.amount ?? "").replace(".", ","),
    currency: record?.currency ?? prefill?.currency ?? "TRY",
    record_date: record?.record_date ?? prefill?.record_date ?? today,
    due_date: record?.due_date ?? prefill?.due_date ?? null,
    status: record?.status === "paid" ? "paid" : "pending",
    paid_on: record?.paid_on ?? null,
    note: record?.note ?? "",
  }));
  const [customer, setCustomer] = useState<PickerOption | null>(() => {
    const id = record?.customer_id ?? prefill?.customer_id;
    const name = record?.customer_name ?? prefill?.customerName;
    return id && name ? { id, label: name } : null;
  });
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState("");
  const [pending, setPending] = useState(false);
  const orderCode = record?.order_code ?? prefill?.orderCode ?? null;
  const linked = Boolean(draft.order_id);

  useEffect(() => {
    let cancelled = false;
    fetchCategories()
      .then((found) => {
        if (cancelled) return;
        setCategories(found);
        setDraft((current) => (current.category ? current : { ...current, category: found[current.kind][0] ?? "" }));
      })
      .catch(() => {
        if (!cancelled) setFormError("Kategoriler yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const searchCustomers = useCallback(async (q: string) => {
    const page = await fetchCustomers({ q, pageSize: 8, sort: "name" });
    return page.items.map((item) => ({ id: item.id, label: item.name, meta: item.email ?? item.phone ?? undefined }));
  }, []);

  function update<K extends keyof RecordPayload>(key: K, value: RecordPayload[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
    setErrors({});
  }

  function switchKind(kind: RecordKind) {
    setDraft((current) => ({ ...current, kind, category: categories?.[kind][0] ?? "" }));
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setFormError("");
    const amount = parseMoney(draft.amount);
    const local: Errors = {};
    if (draft.description.trim().length < 2) local.description = "Açıklama en az 2 karakter olmalı.";
    if (amount === null || Number(amount) <= 0) local.amount = "Geçerli bir tutar girin; örnek 1.250,00";
    if (!draft.category) local.category = "Kategori seçin.";
    setErrors(local);
    const first = (["description", "amount"] as const).find((key) => local[key]);
    if (first || local.category) {
      if (first) form.querySelector<HTMLElement>(`[name="${first}"]`)?.focus();
      return;
    }
    setPending(true);
    const payload: RecordPayload = {
      ...draft,
      amount: amount ?? "0",
      customer_id: customersOn ? (customer?.id ?? null) : draft.customer_id,
      counterparty: customer ? "" : draft.counterparty,
      paid_on: draft.status === "paid" ? (draft.paid_on ?? today) : null,
    };
    try {
      const saved = record ? await updateRecord(record.id, payload) : await createRecord(payload);
      onSaved(saved, record === null);
    } catch (error) {
      if (error instanceof ApiRequestError && (error.fields.amount || error.fields.description || error.fields.category)) {
        setErrors({ amount: error.fields.amount, description: error.fields.description, category: error.fields.category });
      } else {
        setFormError(error instanceof ApiRequestError ? error.message : "Kayıt kaydedilemedi.");
      }
      setPending(false);
    }
  }

  const paidLabel = draft.kind === "income" ? "Tahsil edildi" : "Ödendi";
  const waitingLabel = draft.kind === "income" ? "Tahsilat bekliyor" : "Ödeme bekliyor";

  return (
    <Sheet
      title={record ? "Kaydı düzenle" : orderCode ? `${orderCode} için gelir kaydı` : "Yeni kayıt"}
      description={record ? record.description : "Her değişiklik kayıt geçmişine yazılır; kayıtlar silinmez, iptal edilir."}
      busy={pending}
      onClose={onClose}
      onSubmit={(event) => void onSubmit(event)}
      initialFocus='[name="amount"]'
      footer={
        <>
          <Button type="button" variant="quiet" onClick={onClose} disabled={pending}>
            Vazgeç
          </Button>
          <Button type="submit" pending={pending} pendingLabel="Kaydediliyor" disabled={!categories}>
            {record ? "Değişiklikleri kaydet" : "Kaydı ekle"}
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <fieldset disabled={linked}>
          <legend className="text-[13px] font-medium text-graphite">Tür</legend>
          <div className="mt-2 grid grid-cols-2 gap-1 rounded-xl bg-cloud p-1">
            {(["income", "expense"] as RecordKind[]).map((kind) => (
              <label key={kind}>
                <input type="radio" name="kind" value={kind} checked={draft.kind === kind} onChange={() => switchKind(kind)} className="peer sr-only" />
                <span
                  className={`flex h-9 cursor-pointer items-center justify-center rounded-[9px] text-[13px] font-semibold text-slate transition-colors peer-checked:bg-surface peer-checked:shadow-[0_1px_3px_rgba(16,19,28,0.12)] peer-focus-visible:outline-2 peer-focus-visible:outline-violet peer-disabled:cursor-not-allowed ${
                    kind === "income" ? "peer-checked:text-success-text" : "peer-checked:text-error-text"
                  }`}
                >
                  {kindLabels[kind]}
                </span>
              </label>
            ))}
          </div>
          {linked ? <p className="mt-1.5 text-[12px] text-slate">Siparişe bağlı kayıt her zaman gelirdir.</p> : null}
        </fieldset>

        <div className="grid grid-cols-[minmax(0,1fr)_110px] gap-3">
          <Field
            label="Tutar"
            name="amount"
            inputMode="decimal"
            autoComplete="off"
            placeholder="0,00"
            value={draft.amount}
            error={errors.amount}
            onValue={(value) => update("amount", value)}
          />
          <div>
            <label htmlFor="record-currency" className="text-[13px] font-medium text-graphite">
              Para birimi
            </label>
            <select id="record-currency" value={draft.currency} onChange={(event) => update("currency", event.target.value as Currency)} className={control}>
              {currencies.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label htmlFor="record-category" className="text-[13px] font-medium text-graphite">
            Kategori
          </label>
          <select
            id="record-category"
            value={draft.category}
            onChange={(event) => update("category", event.target.value)}
            aria-invalid={errors.category ? true : undefined}
            className={control}
          >
            {(categories?.[draft.kind] ?? []).map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          {errors.category ? <p className="mt-1.5 text-[13px] text-error-text">{errors.category}</p> : null}
        </div>

        <Field label="Açıklama" name="description" maxLength={200} value={draft.description} error={errors.description} onValue={(value) => update("description", value)} />

        {customersOn ? (
          <Picker
            label="Müşteri (isteğe bağlı)"
            name="customer"
            value={customer}
            onChange={setCustomer}
            search={searchCustomers}
            create={quickCustomer}
            placeholder="Müşteri adıyla arayın"
            emptyText="Eşleşen müşteri yok."
          />
        ) : null}
        {!customer ? (
          <Field
            label={draft.kind === "income" ? "Kimden (isteğe bağlı)" : "Kime (isteğe bağlı)"}
            name="counterparty"
            maxLength={160}
            placeholder={draft.kind === "income" ? "Örnek: perakende müşteri" : "Örnek: tedarikçi veya kurum adı"}
            value={draft.counterparty}
            onValue={(value) => update("counterparty", value)}
          />
        ) : null}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="record-date" className="text-[13px] font-medium text-graphite">
              Kayıt tarihi
            </label>
            <input id="record-date" type="date" required value={draft.record_date} onChange={(event) => update("record_date", event.target.value || today)} className={control} />
          </div>
          <div>
            <label htmlFor="record-due" className="text-[13px] font-medium text-graphite">
              Vade (isteğe bağlı)
            </label>
            <input id="record-due" type="date" value={draft.due_date ?? ""} onChange={(event) => update("due_date", event.target.value || null)} className={control} />
          </div>
        </div>

        <fieldset>
          <legend className="text-[13px] font-medium text-graphite">Durum</legend>
          <div className="mt-2 grid grid-cols-2 gap-1 rounded-xl bg-cloud p-1">
            {(["pending", "paid"] as const).map((status) => (
              <label key={status}>
                <input type="radio" name="status" value={status} checked={draft.status === status} onChange={() => update("status", status)} className="peer sr-only" />
                <span className="flex h-9 cursor-pointer items-center justify-center rounded-[9px] text-[13px] font-semibold text-slate transition-colors peer-checked:bg-surface peer-checked:text-graphite peer-checked:shadow-[0_1px_3px_rgba(16,19,28,0.12)] peer-focus-visible:outline-2 peer-focus-visible:outline-violet">
                  {status === "paid" ? paidLabel : waitingLabel}
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        {draft.status === "paid" ? (
          <div>
            <label htmlFor="record-paid" className="text-[13px] font-medium text-graphite">
              {draft.kind === "income" ? "Tahsilat tarihi" : "Ödeme tarihi"}
            </label>
            <input id="record-paid" type="date" value={draft.paid_on ?? today} onChange={(event) => update("paid_on", event.target.value || today)} className={control} />
          </div>
        ) : null}

        <TextArea label="Not" name="note" rows={3} maxLength={1000} value={draft.note} onValue={(value) => update("note", value)} />
        {formError ? <Alert tone="error">{formError}</Alert> : null}
      </div>
    </Sheet>
  );
}
