import { ApiRequestError, getJson, isRecord, postJson, sendJson } from "./http.ts";
import type { CurrentUser } from "./auth.ts";
import { moduleShortNames, type ModuleKey } from "./modules.ts";

export type Role = "owner" | "admin" | "member";
export type Level = "view" | "edit";
export type Permissions = Record<string, Level>;
export type TeamMember = { user_id: string; name: string; email: string; role: Role; joined_at: string; me: boolean; permissions: Permissions | null };
export type GrantableModule = { key: string; name: string; requires: string[] };
export const levelLabels: Record<Level, string> = { view: "Görüntüleme", edit: "Düzenleme" };
export type MailStatus = "queued" | "handed_off" | "sent" | "failed";
export type Invitation = {
  id: string;
  email: string;
  role: "admin" | "member";
  expires_at: string;
  invited_by: string | null;
  created_at: string;
  email_status: MailStatus | null;
  email_error: string | null;
  permissions: Permissions | null;
};
export type JoinRequest = { id: string; name: string; email: string; position: string | null; note: string | null; email_verified: boolean; created_at: string };
export type Team = {
  members: TeamMember[];
  invitations: Invitation[];
  can_manage: boolean;
  grantable: GrantableModule[];
  join_code: string | null;
  join_requests: JoinRequest[];
};

export async function renewJoinCode(): Promise<Team> {
  return readTeam(await postJson("/api/v1/team/join-code"));
}

export async function approveJoin(id: string, permissions: Permissions): Promise<Team> {
  return readTeam(await postJson(`/api/v1/team/join-requests/${id}/approve`, { permissions }));
}

export async function rejectJoin(id: string): Promise<Team> {
  return readTeam(await postJson(`/api/v1/team/join-requests/${id}/reject`));
}
export type InvitationCreated = { invitation: Invitation; email_sent: false; email_queued: boolean; message: string; invite_path: string | null };
export const mailStatusLabels: Record<MailStatus, string> = {
  queued: "E-posta sırada",
  handed_off: "E-posta n8n'e iletildi",
  sent: "E-posta gönderildi",
  failed: "E-posta gönderilemedi",
};
export type InvitationPreview = { company_name: string; email: string; role: "admin" | "member"; invited_by: string | null; expires_at: string };

export const roleLabels: Record<Role, string> = { owner: "Sahip", admin: "Yönetici", member: "Üye" };
export const roleHints: Record<"admin" | "member", string> = {
  admin: "Modül tercihlerini ve ekibi yönetebilir.",
  member: "Yalnızca aşağıda seçtiğiniz modülleri görür.",
};

/** Adds view access to the modules a granted module depends on, the same way the server does. */
export function withDependencies(grants: Permissions, grantable: GrantableModule[]): Permissions {
  const byKey = new Map(grantable.map((item) => [item.key, item]));
  const result: Permissions = { ...grants };
  const pending = Object.keys(grants);
  while (pending.length > 0) {
    for (const required of byKey.get(pending.pop() ?? "")?.requires ?? []) {
      if (!result[required]) {
        result[required] = "view";
        pending.push(required);
      }
    }
  }
  return result;
}

export function describePermissions(permissions: Permissions | null, grantable: GrantableModule[]): string {
  const names = new Map<string, string>(grantable.map((item) => [item.key, item.name]));
  const parts = Object.entries(permissions ?? {}).map(
    ([key, level]) => `${names.get(key) ?? moduleShortNames[key as ModuleKey] ?? key} (${levelLabels[level].toLocaleLowerCase("tr")})`,
  );
  return parts.length ? parts.join(", ") : "Hiçbir modüle erişimi yok";
}

export async function savePermissions(userId: string, permissions: Permissions): Promise<Team> {
  return readTeam(await sendJson("PUT", `/api/v1/team/members/${userId}/permissions`, { permissions }));
}

function readTeam(payload: unknown): Team {
  if (!isRecord(payload) || !Array.isArray(payload.members)) throw new ApiRequestError(500, "Ekip bilgisi okunamadı.");
  return payload as Team;
}

export async function fetchTeam(): Promise<Team> {
  return readTeam(await getJson("/api/v1/team"));
}

export async function inviteMember(email: string, role: "admin" | "member", permissions: Permissions = {}): Promise<InvitationCreated> {
  const payload = await postJson("/api/v1/team/invitations", { email, role, ...(role === "member" ? { permissions } : {}) });
  if (!isRecord(payload) || !isRecord(payload.invitation)) throw new ApiRequestError(500, "Davet okunamadı.");
  return payload as InvitationCreated;
}

export async function revokeInvitation(id: string): Promise<void> {
  await sendJson("DELETE", `/api/v1/team/invitations/${id}`);
}

export async function changeRole(userId: string, role: "admin" | "member"): Promise<Team> {
  return readTeam(await sendJson("PUT", `/api/v1/team/members/${userId}`, { role }));
}

export async function removeMember(userId: string): Promise<Team> {
  return readTeam(await sendJson("DELETE", `/api/v1/team/members/${userId}`));
}

export async function previewInvitation(token: string): Promise<InvitationPreview> {
  const payload = await getJson(`/api/v1/auth/invitations/preview?token=${encodeURIComponent(token)}`);
  if (!isRecord(payload) || typeof payload.company_name !== "string") throw new ApiRequestError(500, "Davet okunamadı.");
  return payload as InvitationPreview;
}

export async function acceptInvitation(input: { token: string; first_name: string; last_name: string; password: string }): Promise<CurrentUser> {
  const payload = await postJson("/api/v1/auth/invitations/accept", input);
  if (!isRecord(payload) || typeof payload.id !== "string") throw new ApiRequestError(500, "Hesap okunamadı.");
  return payload as CurrentUser;
}
