import { ApiRequestError, getJson, isRecord, postJson, sendJson } from "./http.ts";

export type TicketCategory = "question" | "bug" | "request" | "account" | "complaint" | "notice";
export type CustomerCategory = Exclude<TicketCategory, "notice">;
export type TicketStatus = "open" | "answered" | "closed";

export type Ticket = {
  id: string;
  code: string;
  subject: string;
  category: TicketCategory;
  status: TicketStatus;
  created_by_name: string;
  message_count: number;
  last_message_at: string;
  created_at: string;
  company_id: string | null;
  company_name: string | null;
  opened_by_staff: boolean;
};

export type TicketMessage = { id: string; author_kind: "customer" | "staff"; author_name: string; body: string; created_at: string };
export type TicketDetail = Ticket & { messages: TicketMessage[]; can_reply: boolean };
export type TicketList = { items: Ticket[]; open: number; answered: number; closed: number };

export type AdminOverview = {
  companies: number;
  active_companies: number;
  setup_pending: number;
  users: number;
  signups_30d: number;
  open_tickets: number;
  answered_tickets: number;
  pending_closures: number;
};

export type AdminCompany = {
  id: string;
  name: string;
  slug: string;
  status: string;
  created_at: string;
  setup_completed: boolean;
  owner_name: string;
  owner_email: string;
  members: number;
  modules: number;
  last_activity_at: string | null;
  open_tickets: number;
};

export const categoryLabels: Record<TicketCategory, string> = {
  question: "Soru",
  bug: "Hata bildirimi",
  request: "Özellik isteği",
  account: "Hesap ve erişim",
  complaint: "Şikâyet",
  notice: "LUMINOVA mesajı",
};

export type AdminCompanyDetail = AdminCompany & {
  sector: string | null;
  team_size: string | null;
  module_list: { key: string; name: string; enabled_at: string | null }[];
  people: { name: string; email: string; role: "owner" | "admin" | "member"; joined_at: string }[];
  pending_join_requests: number;
  pending_invitations: number;
};

export async function fetchAdminCompany(id: string): Promise<AdminCompanyDetail> {
  const payload = await getJson(`/api/v1/admin/companies/${id}`);
  if (!isRecord(payload) || !Array.isArray(payload.people)) throw new ApiRequestError(500, "Şirket okunamadı.");
  return payload as AdminCompanyDetail;
}

export async function messageCompany(id: string, subject: string, body: string): Promise<TicketDetail> {
  return detail(await postJson(`/api/v1/admin/companies/${id}/messages`, { subject, body }));
}

export async function deleteCompany(id: string, confirmName: string): Promise<void> {
  await sendJson("DELETE", `/api/v1/admin/companies/${id}`, { confirm_name: confirmName });
}

export const statusLabels: Record<TicketStatus, string> = { open: "Yanıt bekliyor", answered: "Yanıtlandı", closed: "Kapandı" };

export const statusTones: Record<TicketStatus, string> = {
  open: "bg-warning/10 text-warning-text",
  answered: "bg-violet/10 text-violet",
  closed: "bg-cloud text-slate ring-1 ring-inset ring-mist/70",
};

function list(payload: unknown): TicketList {
  if (!isRecord(payload) || !Array.isArray(payload.items)) throw new ApiRequestError(500, "Destek talepleri okunamadı.");
  return payload as TicketList;
}

function detail(payload: unknown): TicketDetail {
  if (!isRecord(payload) || !Array.isArray(payload.messages)) throw new ApiRequestError(500, "Destek talebi okunamadı.");
  return payload as TicketDetail;
}

export async function fetchTickets(): Promise<TicketList> {
  return list(await getJson("/api/v1/support/tickets"));
}

export async function fetchTicket(id: string): Promise<TicketDetail> {
  return detail(await getJson(`/api/v1/support/tickets/${id}`));
}

export async function openTicket(payload: { subject: string; category: CustomerCategory; body: string }): Promise<TicketDetail> {
  return detail(await postJson("/api/v1/support/tickets", payload));
}

export async function writeMessage(id: string, body: string): Promise<TicketDetail> {
  return detail(await postJson(`/api/v1/support/tickets/${id}/messages`, { body }));
}

export async function closeTicket(id: string): Promise<TicketDetail> {
  return detail(await postJson(`/api/v1/support/tickets/${id}/close`));
}

export async function fetchAdminOverview(): Promise<AdminOverview> {
  const payload = await getJson("/api/v1/admin/overview");
  if (!isRecord(payload) || typeof payload.companies !== "number") throw new ApiRequestError(500, "Özet okunamadı.");
  return payload as AdminOverview;
}

export async function fetchAdminCompanies(q: string, page: number): Promise<{ items: AdminCompany[]; total: number }> {
  const params = new URLSearchParams({ page: String(page) });
  if (q.trim()) params.set("q", q.trim());
  const payload = await getJson(`/api/v1/admin/companies?${params}`);
  if (!isRecord(payload) || !Array.isArray(payload.items)) throw new ApiRequestError(500, "Şirketler okunamadı.");
  return payload as { items: AdminCompany[]; total: number };
}

export async function fetchStaffTickets(status: TicketStatus | null): Promise<TicketList> {
  return list(await getJson(`/api/v1/admin/support/tickets${status ? `?status=${status}` : ""}`));
}

export async function fetchStaffTicket(id: string): Promise<TicketDetail> {
  return detail(await getJson(`/api/v1/admin/support/tickets/${id}`));
}

export async function staffReply(id: string, body: string): Promise<TicketDetail> {
  return detail(await postJson(`/api/v1/admin/support/tickets/${id}/reply`, { body }));
}

export async function staffClose(id: string): Promise<TicketDetail> {
  return detail(await postJson(`/api/v1/admin/support/tickets/${id}/close`));
}
