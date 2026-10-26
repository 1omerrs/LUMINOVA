import { ApiRequestError, getJson, isRecord, postJson, sendJson } from "./http.ts";

export type OrderStatus = "draft" | "confirmed" | "fulfilled" | "cancelled";
export type Currency = "TRY" | "USD" | "EUR";
export type VatRate = 0 | 1 | 10 | 20;
export type OrderSort = "-created_at" | "-order_date" | "order_date" | "-total" | "number";
export type OrderAction = "confirm" | "fulfil" | "cancel";

export type OrderSummary = {
  id: string;
  number: number;
  code: string;
  customer_id: string;
  customer_name: string;
  status: OrderStatus;
  currency: Currency;
  order_date: string;
  total: string;
  item_count: number;
  created_at: string;
};

export type OrderLine = {
  id: string;
  position: number;
  product_id: string | null;
  product_sku: string | null;
  product_unit: string | null;
  description: string;
  quantity: string;
  unit_price: string;
  vat_rate: VatRate;
  discount_rate: string;
  line_discount: string;
  line_subtotal: string;
  line_vat: string;
  line_total: string;
};

export type OrderEvent = { from_status: OrderStatus | null; to_status: OrderStatus; note: string | null; actor: string | null; created_at: string };

export type StockCheck = {
  product_id: string;
  name: string;
  unit: string;
  needed: string;
  on_hand: string;
  reserved_elsewhere: string;
  available: string;
  short: string;
  incoming: string;
};

export type OrderDetail = OrderSummary & {
  note: string | null;
  subtotal: string;
  discount_total: string;
  vat_total: string;
  stock_posted: boolean;
  source_quote_id: string | null;
  source_quote_code: string | null;
  stock_check: StockCheck[];
  automation: string[];
  items: OrderLine[];
  events: OrderEvent[];
};

export type LineInput = { product_id: string | null; description: string; quantity: string; unit_price: string; vat_rate: VatRate; discount_rate: string };

export type OrderPayload = {
  customer_id: string;
  currency: Currency;
  order_date: string;
  note: string;
  items: LineInput[];
};

export type IncomeOn = "off" | "confirmed" | "fulfilled";
export type SalesRules = {
  income_on: IncomeOn;
  income_due_days: number | null;
  confirm_template_id: string | null;
  confirm_template_name: string | null;
  production_on_shortage: boolean;
  finance_on: boolean;
  tasks_on: boolean;
  production_on: boolean;
  updated_at: string | null;
};

export async function fetchSalesRules(): Promise<SalesRules> {
  const payload = await getJson("/api/v1/sales/rules");
  if (!isRecord(payload) || typeof payload.income_on !== "string") throw new ApiRequestError(500, "Satış kuralları okunamadı.");
  return payload as SalesRules;
}

export async function saveSalesRules(
  rules: Pick<SalesRules, "income_on" | "income_due_days" | "confirm_template_id" | "production_on_shortage">,
): Promise<SalesRules> {
  return (await sendJson("PUT", "/api/v1/sales/rules", rules)) as SalesRules;
}

export function percentText(value: string): string {
  return `%${value.replace(".", ",")}`;
}

export type SalesSummary = Record<OrderStatus, number>;

export const statusLabels: Record<OrderStatus, string> = {
  draft: "Taslak",
  confirmed: "Onaylandı",
  fulfilled: "Teslim edildi",
  cancelled: "İptal edildi",
};

export const statusTone: Record<OrderStatus, string> = {
  draft: "bg-cloud text-slate ring-1 ring-inset ring-mist",
  confirmed: "bg-violet/10 text-violet",
  fulfilled: "bg-success/10 text-success-text",
  cancelled: "bg-error/[0.07] text-error-text",
};

export const sortLabels: Record<OrderSort, string> = {
  "-created_at": "En yeni",
  "-order_date": "Sipariş tarihi (yeni)",
  order_date: "Sipariş tarihi (eski)",
  "-total": "Tutar (yüksekten)",
  number: "Sipariş numarası",
};

export const currencies: Currency[] = ["TRY", "USD", "EUR"];
export const vatRates: VatRate[] = [20, 10, 1, 0];

const moneyFormats = new Map<Currency, Intl.NumberFormat>();

export function formatMoney(value: string | number, currency: Currency): string {
  let format = moneyFormats.get(currency);
  if (!format) {
    format = new Intl.NumberFormat("tr-TR", { style: "currency", currency, minimumFractionDigits: 2, maximumFractionDigits: 2 });
    moneyFormats.set(currency, format);
  }
  return format.format(Number(value));
}

export function parseMoney(input: string): string | null {
  let cleaned = input.trim().replace(/[\s₺]/g, "");
  if (cleaned.includes(",")) {
    if (!/^\d{1,3}(\.\d{3})*,\d{1,2}$|^\d+,\d{1,2}$/.test(cleaned)) return null;
    cleaned = cleaned.replace(/\./g, "").replace(",", ".");
  }
  if (!/^\d{1,13}(\.\d{1,2})?$/.test(cleaned)) return null;
  return cleaned;
}

const dateFormat = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "short", year: "numeric" });

export function formatDate(iso: string): string {
  return dateFormat.format(new Date(`${iso}T00:00:00`));
}

export async function fetchOrders(options: { q?: string; status?: OrderStatus | null; sort?: OrderSort; page?: number; pageSize?: number }) {
  const params = new URLSearchParams();
  if (options.q) params.set("q", options.q);
  if (options.status) params.set("status", options.status);
  if (options.sort) params.set("sort", options.sort);
  if (options.page) params.set("page", String(options.page));
  if (options.pageSize) params.set("page_size", String(options.pageSize));
  const payload = await getJson(`/api/v1/sales/orders?${params.toString()}`);
  if (!isRecord(payload) || !Array.isArray(payload.items) || typeof payload.total !== "number") {
    throw new ApiRequestError(500, "Sipariş listesi okunamadı.");
  }
  return { items: payload.items as OrderSummary[], total: payload.total, page: Number(payload.page), page_size: Number(payload.page_size) };
}

export async function fetchSalesSummary(): Promise<SalesSummary> {
  const payload = await getJson("/api/v1/sales/summary");
  if (!isRecord(payload) || typeof payload.draft !== "number") throw new ApiRequestError(500, "Satış özeti okunamadı.");
  return payload as SalesSummary;
}

export async function fetchOrder(id: string): Promise<OrderDetail> {
  return readDetail(await getJson(`/api/v1/sales/orders/${id}`));
}

export async function createOrder(payload: OrderPayload): Promise<OrderDetail> {
  return readDetail(await postJson("/api/v1/sales/orders", payload));
}

export async function updateOrder(id: string, payload: OrderPayload): Promise<OrderDetail> {
  return readDetail(await sendJson("PUT", `/api/v1/sales/orders/${id}`, payload));
}

export async function transitionOrder(id: string, action: OrderAction, note: string): Promise<OrderDetail> {
  return readDetail(await postJson(`/api/v1/sales/orders/${id}/${action}`, note.trim() ? { note } : undefined));
}

function readDetail(payload: unknown): OrderDetail {
  if (!isRecord(payload) || typeof payload.id !== "string" || !Array.isArray(payload.items) || !Array.isArray(payload.events)) {
    throw new ApiRequestError(500, "Sipariş okunamadı.");
  }
  return payload as OrderDetail;
}
