import { ApiRequestError, getJson, isRecord, postJson, sendJson } from "./http.ts";
import type { Currency, OrderLine, VatRate } from "./sales.ts";
import type { MailStatus } from "./team.ts";

export type QuoteStatus = "draft" | "sent" | "accepted" | "rejected";
export type QuoteSort = "-created_at" | "-quote_date" | "-total" | "number";
export type QuoteAction = "send" | "accept" | "reject" | "convert";

export type QuoteSummaryItem = {
  id: string;
  number: number;
  code: string;
  customer_id: string;
  customer_name: string;
  status: QuoteStatus;
  expired: boolean;
  currency: Currency;
  quote_date: string;
  valid_until: string | null;
  total: string;
  item_count: number;
  order_id: string | null;
  order_code: string | null;
  created_at: string;
};

export type QuoteDetail = QuoteSummaryItem & {
  note: string | null;
  subtotal: string;
  discount_total: string;
  vat_total: string;
  sent_at: string | null;
  decided_at: string | null;
  decided_by: "staff" | "customer" | null;
  customer_note: string | null;
  customer_email: string | null;
  email_status: MailStatus | null;
  email_error: string | null;
  share_path: string | null;
  email_notice: string | null;
  items: OrderLine[];
};

export type SendOptions = { email: boolean; message: string };

export type PublicQuote = {
  company_name: string;
  code: string;
  customer_name: string;
  status: QuoteStatus;
  expired: boolean;
  can_decide: boolean;
  currency: Currency;
  quote_date: string;
  valid_until: string | null;
  note: string | null;
  subtotal: string;
  discount_total: string;
  vat_total: string;
  total: string;
  decided_at: string | null;
  decided_by: "staff" | "customer" | null;
  customer_note: string | null;
  items: { description: string; quantity: string; unit: string | null; unit_price: string; vat_rate: number; discount_rate: string; line_total: string }[];
};

export type QuotePage = { items: QuoteSummaryItem[]; total: number; page: number; page_size: number };
export type QuoteSummary = Record<QuoteStatus, number> & { open_value: string };
export type QuotePayload = {
  customer_id: string;
  currency: Currency;
  quote_date: string;
  valid_until: string | null;
  note: string;
  items: { product_id: string | null; description: string; quantity: string; unit_price: string; vat_rate: VatRate }[];
};

export const quoteStatusLabels: Record<QuoteStatus, string> = { draft: "Taslak", sent: "Gönderildi", accepted: "Kabul edildi", rejected: "Reddedildi" };
export const quoteStatusTone: Record<QuoteStatus, string> = {
  draft: "bg-cloud text-slate ring-1 ring-inset ring-mist",
  sent: "bg-violet/10 text-violet",
  accepted: "bg-success/10 text-success-text",
  rejected: "bg-error/[0.07] text-error-text",
};
export const quoteSortLabels: Record<QuoteSort, string> = {
  "-created_at": "En yeni",
  "-quote_date": "Teklif tarihi",
  "-total": "Tutar (yüksekten)",
  number: "Teklif numarası",
};

export async function fetchQuotes(options: { q?: string; status?: QuoteStatus | null; sort?: QuoteSort; page?: number; pageSize?: number }): Promise<QuotePage> {
  const params = new URLSearchParams();
  if (options.q) params.set("q", options.q);
  if (options.status) params.set("status", options.status);
  if (options.sort) params.set("sort", options.sort);
  if (options.page) params.set("page", String(options.page));
  if (options.pageSize) params.set("page_size", String(options.pageSize));
  const payload = await getJson(`/api/v1/quotes?${params.toString()}`);
  if (!isRecord(payload) || !Array.isArray(payload.items)) throw new ApiRequestError(500, "Teklif listesi okunamadı.");
  return payload as QuotePage;
}

export async function fetchQuoteSummary(): Promise<QuoteSummary> {
  const payload = await getJson("/api/v1/quotes/summary");
  if (!isRecord(payload) || typeof payload.draft !== "number") throw new ApiRequestError(500, "Teklif özeti okunamadı.");
  return payload as QuoteSummary;
}

export async function fetchQuote(id: string): Promise<QuoteDetail> {
  return readQuote(await getJson(`/api/v1/quotes/${id}`));
}

export async function createQuote(payload: QuotePayload): Promise<QuoteDetail> {
  return readQuote(await postJson("/api/v1/quotes", payload));
}

export async function updateQuote(id: string, payload: QuotePayload): Promise<QuoteDetail> {
  return readQuote(await sendJson("PUT", `/api/v1/quotes/${id}`, payload));
}

export async function quoteAction(id: string, action: QuoteAction): Promise<QuoteDetail> {
  return readQuote(await postJson(`/api/v1/quotes/${id}/${action}`, undefined));
}

export async function sendQuote(id: string, options: SendOptions, resend = false): Promise<QuoteDetail> {
  return readQuote(await postJson(`/api/v1/quotes/${id}/${resend ? "resend" : "send"}`, { email: options.email, message: options.message.trim() || null }));
}

function readPublic(payload: unknown): PublicQuote {
  if (!isRecord(payload) || typeof payload.code !== "string" || !Array.isArray(payload.items)) throw new ApiRequestError(500, "Teklif okunamadı.");
  return payload as PublicQuote;
}

export async function fetchPublicQuote(token: string): Promise<PublicQuote> {
  return readPublic(await getJson(`/api/v1/public/quotes/${encodeURIComponent(token)}`));
}

export async function decidePublicQuote(token: string, decision: "accept" | "reject", note: string): Promise<PublicQuote> {
  return readPublic(await postJson(`/api/v1/public/quotes/${encodeURIComponent(token)}/decision`, { decision, note: note.trim() || null }));
}

function readQuote(payload: unknown): QuoteDetail {
  if (!isRecord(payload) || typeof payload.id !== "string" || !Array.isArray(payload.items)) throw new ApiRequestError(500, "Teklif okunamadı.");
  return payload as QuoteDetail;
}
