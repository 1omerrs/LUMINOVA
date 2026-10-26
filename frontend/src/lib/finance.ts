import { ApiRequestError, getJson, isRecord, postJson, sendJson } from "./http.ts";
import type { Currency } from "./sales.ts";

export type RecordKind = "income" | "expense";
export type RecordStatus = "pending" | "partial" | "paid" | "cancelled";
export type PaymentMethod = "cash" | "transfer" | "card" | "check" | "other";
export const methodLabels: Record<PaymentMethod, string> = { cash: "Nakit", transfer: "Havale/EFT", card: "Kart", check: "Çek/senet", other: "Diğer" };
export type Payment = { id: string; amount: string; paid_on: string; method: PaymentMethod; note: string | null; actor: string | null; created_at: string };
export type Balance = {
  customer_id: string | null;
  name: string;
  currency: Currency;
  open_amount: string;
  overdue_amount: string;
  records: number;
  oldest_due: string | null;
  last_payment: string | null;
};
export type CashflowWeek = { week_start: string; week_end: string; actual_in: string; actual_out: string; expected_in: string; expected_out: string };
export type Cashflow = {
  currency: Currency;
  today: string;
  overdue_in: string;
  overdue_out: string;
  undated_in: string;
  undated_out: string;
  weeks: CashflowWeek[];
  opening_amount: string | null;
  opening_as_of: string | null;
  cash_now: string | null;
};
export type RecordSort = "-record_date" | "record_date" | "-amount" | "due_date";

export type FinanceRecord = {
  id: string;
  kind: RecordKind;
  category: string;
  description: string;
  counterparty: string | null;
  customer_id: string | null;
  customer_name: string | null;
  order_id: string | null;
  order_code: string | null;
  amount: string;
  paid_amount: string;
  remaining: string;
  currency: Currency;
  record_date: string;
  due_date: string | null;
  status: RecordStatus;
  paid_on: string | null;
  overdue: boolean;
  note: string | null;
  cancel_reason: string | null;
  created_at: string;
  updated_at: string;
};

export type Revision = {
  revision: number;
  action: "created" | "updated" | "cancelled" | "payment_added" | "payment_removed";
  changes: Record<string, { from: string | null; to: string | null }>;
  reason: string | null;
  actor: string | null;
  created_at: string;
};

export type RecordDetail = FinanceRecord & { revisions: Revision[]; payments: Payment[] };
export type RecordPage = { items: FinanceRecord[]; total: number; page: number; page_size: number; today: string };
export type CurrencyTotals = { currency: Currency; income: string; expense: string; net: string; receivable: string; payable: string };
export type FinanceSummary = {
  today: string;
  period_from: string;
  period_to: string;
  totals: CurrencyTotals[];
  overdue_receivables: number;
  overdue_payables: number;
};
export type Categories = Record<RecordKind, string[]>;
export type RecordPayload = {
  kind: RecordKind;
  category: string;
  description: string;
  counterparty: string;
  customer_id: string | null;
  order_id: string | null;
  amount: string;
  currency: Currency;
  record_date: string;
  due_date: string | null;
  status: "pending" | "paid";
  paid_on: string | null;
  note: string;
};

export const kindLabels: Record<RecordKind, string> = { income: "Gelir", expense: "Gider" };

export function statusLabel(record: Pick<FinanceRecord, "kind" | "status">): string {
  if (record.status === "cancelled") return "İptal edildi";
  if (record.status === "paid") return record.kind === "income" ? "Tahsil edildi" : "Ödendi";
  if (record.status === "partial") return record.kind === "income" ? "Kısmen tahsil edildi" : "Kısmen ödendi";
  return record.kind === "income" ? "Tahsilat bekliyor" : "Ödeme bekliyor";
}

export function statusTone(record: Pick<FinanceRecord, "status" | "overdue">): string {
  if (record.status === "cancelled") return "bg-cloud text-slate ring-1 ring-inset ring-mist";
  if (record.status === "paid") return "bg-success/10 text-success-text";
  if (record.status === "partial" && !record.overdue) return "bg-violet/10 text-violet";
  return record.overdue ? "bg-error/[0.08] text-error-text" : "bg-warning/10 text-warning-text";
}

export const fieldLabels: Record<string, string> = {
  kind: "Tür",
  category: "Kategori",
  description: "Açıklama",
  counterparty: "Karşı taraf",
  customer_id: "Müşteri",
  amount: "Tutar",
  currency: "Para birimi",
  record_date: "Kayıt tarihi",
  due_date: "Vade",
  status: "Durum",
  paid_on: "Ödeme tarihi",
  paid_amount: "Ödenen",
  note: "Not",
};

export const sortLabels: Record<RecordSort, string> = {
  "-record_date": "Tarih (yeni)",
  record_date: "Tarih (eski)",
  "-amount": "Tutar (yüksekten)",
  due_date: "Vade (yakın)",
};

export function monthRange(anchor: string, offset = 0): { from: string; to: string; label: string } {
  const [year, month] = anchor.split("-").map(Number);
  const start = new Date(Date.UTC(year, month - 1 + offset, 1));
  const end = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 0));
  const label = new Intl.DateTimeFormat("tr-TR", { month: "long", year: "numeric", timeZone: "UTC" }).format(start);
  return { from: start.toISOString().slice(0, 10), to: end.toISOString().slice(0, 10), label };
}

type ListOptions = {
  q?: string;
  kind?: RecordKind | null;
  status?: RecordStatus | null;
  overdue?: boolean;
  from?: string | null;
  to?: string | null;
  orderId?: string;
  customerId?: string;
  open?: boolean;
  dueTo?: string;
  sort?: RecordSort;
  page?: number;
  pageSize?: number;
};

export async function fetchRecords(options: ListOptions): Promise<RecordPage> {
  const params = new URLSearchParams();
  if (options.q) params.set("q", options.q);
  if (options.kind) params.set("kind", options.kind);
  if (options.status) params.set("status", options.status);
  if (options.overdue) params.set("overdue", "true");
  if (options.from) params.set("from", options.from);
  if (options.to) params.set("to", options.to);
  if (options.orderId) params.set("order_id", options.orderId);
  if (options.customerId) params.set("customer_id", options.customerId);
  if (options.open) params.set("open", "true");
  if (options.dueTo) params.set("due_to", options.dueTo);
  if (options.sort) params.set("sort", options.sort);
  if (options.page) params.set("page", String(options.page));
  if (options.pageSize) params.set("page_size", String(options.pageSize));
  const payload = await getJson(`/api/v1/finance/records?${params.toString()}`);
  if (!isRecord(payload) || !Array.isArray(payload.items) || typeof payload.total !== "number") throw new ApiRequestError(500, "Kayıt listesi okunamadı.");
  return payload as RecordPage;
}

export async function fetchFinanceSummary(range?: { from: string; to: string }): Promise<FinanceSummary> {
  const params = range ? `?from=${range.from}&to=${range.to}` : "";
  const payload = await getJson(`/api/v1/finance/summary${params}`);
  if (!isRecord(payload) || !Array.isArray(payload.totals)) throw new ApiRequestError(500, "Finans özeti okunamadı.");
  return payload as FinanceSummary;
}

export async function fetchCategories(): Promise<Categories> {
  const payload = await getJson("/api/v1/finance/categories");
  if (!isRecord(payload) || !Array.isArray(payload.income) || !Array.isArray(payload.expense)) throw new ApiRequestError(500, "Kategoriler okunamadı.");
  return payload as Categories;
}

export async function fetchRecord(id: string): Promise<RecordDetail> {
  return readDetail(await getJson(`/api/v1/finance/records/${id}`));
}

export async function createRecord(payload: RecordPayload): Promise<RecordDetail> {
  return readDetail(await postJson("/api/v1/finance/records", payload));
}

export async function updateRecord(id: string, payload: RecordPayload): Promise<RecordDetail> {
  return readDetail(await sendJson("PUT", `/api/v1/finance/records/${id}`, payload));
}

export async function cancelRecord(id: string, reason: string): Promise<RecordDetail> {
  return readDetail(await postJson(`/api/v1/finance/records/${id}/cancel`, { reason }));
}

export async function addPayment(id: string, payment: { amount: string; paid_on: string; method: PaymentMethod; note: string }): Promise<RecordDetail> {
  return readDetail(await postJson(`/api/v1/finance/records/${id}/payments`, payment));
}

export async function removePayment(id: string, paymentId: string): Promise<RecordDetail> {
  return readDetail(await sendJson("DELETE", `/api/v1/finance/records/${id}/payments/${paymentId}`));
}

export async function fetchBalances(): Promise<Balance[]> {
  const payload = await getJson("/api/v1/finance/balances");
  if (!Array.isArray(payload)) throw new ApiRequestError(500, "Bakiyeler okunamadı.");
  return payload as Balance[];
}

export async function fetchCashflow(currency: Currency, weeks = 8, past = 4): Promise<Cashflow> {
  const payload = await getJson(`/api/v1/finance/cashflow?currency=${currency}&weeks=${weeks}&past=${past}`);
  if (!isRecord(payload) || !Array.isArray(payload.weeks)) throw new ApiRequestError(500, "Nakit akışı okunamadı.");
  return payload as Cashflow;
}

export async function saveOpeningBalance(currency: Currency, amount: string, asOf: string): Promise<Cashflow> {
  const payload = await sendJson("PUT", "/api/v1/finance/opening-balance", { currency, amount, as_of: asOf });
  if (!isRecord(payload) || !Array.isArray(payload.weeks)) throw new ApiRequestError(500, "Nakit akışı okunamadı.");
  return payload as Cashflow;
}

export function payloadFrom(record: FinanceRecord, patch: Partial<RecordPayload> = {}): RecordPayload {
  return {
    kind: record.kind,
    category: record.category,
    description: record.description,
    counterparty: record.counterparty ?? "",
    customer_id: record.customer_id,
    order_id: record.order_id,
    amount: record.amount,
    currency: record.currency,
    record_date: record.record_date,
    due_date: record.due_date,
    status: record.status === "paid" ? "paid" : "pending",
    paid_on: record.paid_on,
    note: record.note ?? "",
    ...patch,
  };
}

function readDetail(payload: unknown): RecordDetail {
  if (!isRecord(payload) || typeof payload.id !== "string" || !Array.isArray(payload.revisions)) throw new ApiRequestError(500, "Kayıt okunamadı.");
  return payload as RecordDetail;
}
