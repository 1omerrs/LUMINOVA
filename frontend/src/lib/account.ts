import { ApiRequestError, csrfToken, getJson, isRecord, messageFrom, postJson, sendJson } from "./http.ts";

export type Closure = { id: string; scheduled_for: string; created_at: string; reason: string | null };
export type AdminClosure = {
  id: string;
  company_id: string;
  company_name: string;
  company_slug: string;
  requested_by: string;
  requested_email: string;
  reason: string | null;
  scheduled_for: string;
  created_at: string;
  due: boolean;
};

async function download(path: string, method: "GET" | "POST", fallback: string): Promise<void> {
  const headers: Record<string, string> = {};
  if (method === "POST") headers["X-CSRF-Token"] = await csrfToken();
  let response: Response;
  try {
    response = await fetch(path, { method, credentials: "include", headers });
  } catch {
    throw new ApiRequestError(0, "Sunucuya ulaşılamadı.");
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    throw new ApiRequestError(response.status, messageFrom(payload));
  }
  const name = /filename="([^"]+)"/.exec(response.headers.get("content-disposition") ?? "")?.[1] ?? fallback;
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function downloadWorkspaceExport(): Promise<void> {
  return download("/api/v1/exports/workspace", "POST", "luminova-calisma-alani.zip");
}

export function downloadPersonalExport(): Promise<void> {
  return download("/api/v1/me/export", "GET", "luminova-kisisel-verilerim.json");
}

export async function fetchClosure(): Promise<Closure | null> {
  const payload = await getJson("/api/v1/workspace/closure");
  return isRecord(payload) ? (payload as Closure) : null;
}

export async function requestClosure(password: string, reason: string): Promise<Closure> {
  return (await postJson("/api/v1/workspace/closure", { password, reason: reason.trim() || null })) as Closure;
}

export async function cancelClosure(): Promise<void> {
  await sendJson("DELETE", "/api/v1/workspace/closure");
}

export async function closeAccount(password: string): Promise<void> {
  await postJson("/api/v1/me/close", { password });
}

export async function fetchAdminClosures(): Promise<AdminClosure[]> {
  const payload = await getJson("/api/v1/admin/closures");
  if (!Array.isArray(payload)) throw new ApiRequestError(500, "Kapatma talepleri okunamadı.");
  return payload as AdminClosure[];
}

export async function completeClosure(id: string): Promise<void> {
  await postJson(`/api/v1/admin/closures/${id}/complete`);
}
