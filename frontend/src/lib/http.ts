type FieldErrors = Record<string, string>;

export class ApiRequestError extends Error {
  readonly status: number;
  readonly fields: FieldErrors;

  constructor(status: number, message: string, fields: FieldErrors = {}) {
    super(message);
    this.status = status;
    this.fields = fields;
  }
}

export async function csrfToken(): Promise<string> {
  const response = await fetch("/api/v1/auth/csrf", { credentials: "include" });
  const payload: unknown = await response.json();
  if (!response.ok || !isRecord(payload) || typeof payload.token !== "string") {
    throw new ApiRequestError(response.status, "Güvenlik doğrulaması alınamadı.");
  }
  return payload.token;
}

export async function getJson(path: string): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(path, { credentials: "include", headers: { Accept: "application/json" } });
  } catch {
    throw new ApiRequestError(0, "Sunucuya ulaşılamadı.");
  }
  const payload: unknown = await response.json();
  if (!response.ok) {
    throw new ApiRequestError(response.status, messageFrom(payload), fieldsFrom(payload));
  }
  return payload;
}

export async function postJson(path: string, body?: object): Promise<unknown> {
  return sendJson("POST", path, body);
}

export async function sendJson(method: "POST" | "PUT" | "DELETE", path: string, body?: object): Promise<unknown> {
  const token = await csrfToken();
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      credentials: "include",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRF-Token": token,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiRequestError(0, "Sunucuya ulaşılamadı.");
  }
  if (response.status === 204) {
    return null;
  }
  const payload: unknown = await response.json();
  if (!response.ok) {
    throw new ApiRequestError(response.status, messageFrom(payload), fieldsFrom(payload));
  }
  return payload;
}

export function messageFrom(payload: unknown): string {
  if (!isRecord(payload)) {
    return "İstek tamamlanamadı.";
  }
  if (typeof payload.detail === "string") {
    return payload.detail;
  }
  if (Array.isArray(payload.detail) && payload.detail.length > 0) {
    const first = payload.detail[0];
    if (isRecord(first) && typeof first.msg === "string") {
      return first.msg;
    }
  }
  return "İstek tamamlanamadı.";
}

function fieldsFrom(payload: unknown): FieldErrors {
  if (!isRecord(payload) || !Array.isArray(payload.detail)) {
    return {};
  }
  const fields: FieldErrors = {};
  for (const item of payload.detail) {
    if (!isRecord(item) || !Array.isArray(item.loc) || typeof item.msg !== "string") {
      continue;
    }
    const field = item.loc[item.loc.length - 1];
    if (typeof field === "string" && field !== "body") {
      fields[field] = item.msg;
    }
  }
  return fields;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
