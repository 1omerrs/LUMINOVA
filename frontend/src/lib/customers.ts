import { ApiRequestError, getJson, isRecord, postJson, sendJson } from "./http.ts";

export type Customer = {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  note: string | null;
  created_at: string;
  updated_at: string;
};

export type CustomerPage = { items: Customer[]; total: number; page: number; page_size: number };
export type CustomerSort = "-created_at" | "created_at" | "name" | "-name";
export type CustomerDraft = { name: string; email: string; phone: string; note: string };

export const sortLabels: Record<CustomerSort, string> = {
  "-created_at": "En yeni",
  created_at: "En eski",
  name: "Ada göre (A–Z)",
  "-name": "Ada göre (Z–A)",
};

export const phonePattern = /^\+?[0-9 ()-]{7,40}$/;

export async function fetchCustomers(options: { q?: string; sort?: CustomerSort; page?: number; pageSize?: number }): Promise<CustomerPage> {
  const params = new URLSearchParams();
  if (options.q) params.set("q", options.q);
  if (options.sort) params.set("sort", options.sort);
  if (options.page) params.set("page", String(options.page));
  if (options.pageSize) params.set("page_size", String(options.pageSize));
  const payload = await getJson(`/api/v1/customers?${params.toString()}`);
  if (!isRecord(payload) || !Array.isArray(payload.items) || typeof payload.total !== "number") {
    throw new ApiRequestError(500, "Müşteri listesi okunamadı.");
  }
  return {
    items: payload.items.map(readCustomer),
    total: payload.total,
    page: Number(payload.page),
    page_size: Number(payload.page_size),
  };
}

export async function createCustomer(draft: CustomerDraft): Promise<Customer> {
  return readCustomer(await postJson("/api/v1/customers", draft));
}

export async function updateCustomer(id: string, draft: CustomerDraft): Promise<Customer> {
  return readCustomer(await sendJson("PUT", `/api/v1/customers/${id}`, draft));
}

export async function fetchCustomer(id: string): Promise<Customer> {
  return readCustomer(await getJson(`/api/v1/customers/${id}`));
}

export async function deleteCustomer(id: string): Promise<void> {
  await sendJson("DELETE", `/api/v1/customers/${id}`);
}

export type CustomerMatch = { id: string; name: string; email: string | null; phone: string | null; reason: string };
export type Money = { currency: string; amount: string };
export type OverviewLink = { id: string; code: string; status: string; status_label: string; when: string | null; amount: string | null; currency: string | null };
export type CustomerOverview = {
  enabled: string[];
  order_count: number;
  open_orders: number;
  revenue: Money[];
  orders: OverviewLink[];
  open_quotes: number;
  quotes: OverviewLink[];
  projects: OverviewLink[];
  open_tasks: { id: string; title: string; status: string; due_date: string | null; overdue: boolean }[];
  finance: { receivable: Money[]; collected: Money[]; overdue: number; pending: OverviewLink[] } | null;
  timeline: { kind: string; label: string; at: string; link: string | null }[];
};
export type ImportMapping = { name: number | null; email: number | null; phone: number | null; note: number | null };
export type ImportPreview = { headers: string[]; sample: string[][]; total_rows: number; mapping: ImportMapping };
export type ImportReport = {
  total: number;
  valid: number;
  created: number;
  dry_run: boolean;
  duplicates: { row: number; name: string; reason: string; existing_id: string | null; existing_name: string | null }[];
  errors: { row: number; message: string }[];
};
export type ImportFile = { filename: string; content: string };

export async function fetchMatches(draft: { name: string; email: string; phone: string }, exclude?: string): Promise<CustomerMatch[]> {
  const params = new URLSearchParams({ name: draft.name.trim() });
  if (draft.email.trim()) params.set("email", draft.email.trim());
  if (draft.phone.trim()) params.set("phone", draft.phone.trim());
  if (exclude) params.set("exclude", exclude);
  const payload = await getJson(`/api/v1/customers/matches?${params}`);
  return Array.isArray(payload) ? (payload as CustomerMatch[]) : [];
}

export async function fetchCustomerDetail(id: string): Promise<{ customer: Customer; overview: CustomerOverview }> {
  const payload = await getJson(`/api/v1/customers/${id}/overview`);
  if (!isRecord(payload) || !isRecord(payload.overview)) throw new ApiRequestError(500, "Müşteri özeti okunamadı.");
  return { customer: readCustomer(payload.customer), overview: payload.overview as CustomerOverview };
}

export async function readImportFile(file: File): Promise<ImportFile> {
  const buffer = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let index = 0; index < buffer.length; index += 0x8000) binary += String.fromCharCode(...buffer.subarray(index, index + 0x8000));
  return { filename: file.name, content: btoa(binary) };
}

export async function previewImport(file: ImportFile): Promise<ImportPreview> {
  return (await postJson("/api/v1/customers/import/preview", file)) as ImportPreview;
}

export async function runImport(file: ImportFile, mapping: ImportMapping, dryRun: boolean): Promise<ImportReport> {
  return (await postJson("/api/v1/customers/import", { ...file, mapping, dry_run: dryRun })) as ImportReport;
}

function readCustomer(item: unknown): Customer {
  if (!isRecord(item) || typeof item.id !== "string" || typeof item.name !== "string" || typeof item.created_at !== "string") {
    throw new ApiRequestError(500, "Müşteri kaydı okunamadı.");
  }
  const text = (value: unknown) => (typeof value === "string" ? value : null);
  return {
    id: item.id,
    name: item.name,
    email: text(item.email),
    phone: text(item.phone),
    note: text(item.note),
    created_at: item.created_at,
    updated_at: String(item.updated_at),
  };
}
