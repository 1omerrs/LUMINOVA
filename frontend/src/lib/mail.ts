import { ApiRequestError, getJson, isRecord, postJson } from "./http.ts";
import type { MailStatus } from "./team.ts";

export type MailItem = {
  id: string;
  kind: string;
  kind_label: string;
  to_email: string;
  subject: string;
  company_name: string | null;
  status: MailStatus;
  attempts: number;
  last_error: string | null;
  provider_message_id: string | null;
  retryable: boolean;
  created_at: string;
  handed_off_at: string | null;
  sent_at: string | null;
};
export type MailList = { configured: boolean; webhook_host: string | null; counts: Partial<Record<MailStatus, number>>; items: MailItem[] };

export async function fetchMail(status: MailStatus | null): Promise<MailList> {
  const payload = await getJson(`/api/v1/admin/mail${status ? `?status=${status}` : ""}`);
  if (!isRecord(payload) || !Array.isArray(payload.items)) throw new ApiRequestError(500, "E-posta kuyruğu okunamadı.");
  return payload as MailList;
}

export async function retryMail(id: string): Promise<MailItem> {
  return (await postJson(`/api/v1/admin/mail/${id}/retry`)) as MailItem;
}
