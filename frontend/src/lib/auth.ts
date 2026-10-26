import { ApiRequestError, csrfToken, getJson, isRecord, messageFrom, postJson } from "./http.ts";

export { ApiRequestError } from "./http.ts";

export type CurrentUser = {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  member_since: string;
  role: string;
  company_id: string;
  company_name: string;
  company_slug: string;
  company_timezone: string;
  setup_completed: boolean;
  is_platform_admin: boolean;
  /** The LUMINOVA staff account that only opens /yonetim; company fields are empty strings. */
  staff_only: boolean;
  closure_scheduled_for: string | null;
};

export const sectorOptions: { value: string; label: string }[] = [
  { value: "uretim", label: "Üretim / imalat" },
  { value: "mobilya", label: "Mobilya ve dekorasyon" },
  { value: "insaat", label: "İnşaat ve taahhüt" },
  { value: "perakende", label: "Perakende ve e-ticaret" },
  { value: "gida", label: "Gıda ve restoran" },
  { value: "tekstil", label: "Tekstil ve hazır giyim" },
  { value: "hizmet", label: "Hizmet ve danışmanlık" },
  { value: "teknoloji", label: "Yazılım ve teknoloji" },
  { value: "saglik", label: "Sağlık ve güzellik" },
  { value: "diger", label: "Diğer" },
];
export const teamSizeOptions = ["1", "2-5", "6-20", "21-50", "51+"];

export async function registerMember(input: {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  join_code: string;
  position: string;
  note: string;
}): Promise<RegisterResult> {
  const payload = await postJson("/api/v1/auth/register/member", input);
  if (!isRecord(payload) || typeof payload.message !== "string") throw new ApiRequestError(500, "Hesap yanıtı okunamadı.");
  return { email_sent: false, message: payload.message, verification_path: typeof payload.verification_path === "string" ? payload.verification_path : null };
}

export async function previewJoinCode(code: string): Promise<string> {
  const payload = await getJson(`/api/v1/auth/join/preview?code=${encodeURIComponent(code)}`);
  if (!isRecord(payload) || typeof payload.company_name !== "string") throw new ApiRequestError(500, "Kod doğrulanamadı.");
  return payload.company_name;
}

export type RegisterResult = {
  email_sent: false;
  message: string;
  verification_path: string | null;
};

export type ResetRequestResult = {
  message: string;
  reset_path: string | null;
};

export async function registerAccount(input: {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  company_name: string;
  sector: string | null;
  team_size: string | null;
}): Promise<RegisterResult> {
  const payload = await postJson("/api/v1/auth/register", input);
  if (!isRecord(payload) || payload.email_sent !== false || typeof payload.message !== "string") {
    throw new ApiRequestError(500, "Hesap yanıtı okunamadı.");
  }
  return {
    email_sent: false,
    message: payload.message,
    verification_path: typeof payload.verification_path === "string" ? payload.verification_path : null,
  };
}

export async function verifyEmail(token: string): Promise<string> {
  return readMessage(await postJson("/api/v1/auth/verify-email", { token }));
}

export async function verifyCode(email: string, code: string): Promise<string> {
  return readMessage(await postJson("/api/v1/auth/verify-code", { email, code }));
}

export async function resendCode(email: string): Promise<string> {
  return readMessage(await postJson("/api/v1/auth/verify-code/resend", { email }));
}

export async function loginAccount(email: string, password: string, remember: boolean): Promise<CurrentUser> {
  return readUser(await postJson("/api/v1/auth/login", { email, password, remember }));
}

export async function requestPasswordReset(email: string): Promise<ResetRequestResult> {
  const payload = await postJson("/api/v1/auth/forgot-password", { email });
  if (!isRecord(payload) || typeof payload.message !== "string") {
    throw new ApiRequestError(500, "Yanıt okunamadı.");
  }
  return { message: payload.message, reset_path: typeof payload.reset_path === "string" ? payload.reset_path : null };
}

export async function resetPassword(token: string, password: string): Promise<string> {
  return readMessage(await postJson("/api/v1/auth/reset-password", { token, password }));
}

export async function logoutAccount(): Promise<void> {
  const token = await csrfToken();
  const response = await fetch("/api/v1/auth/logout", {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": token },
  });
  if (!response.ok) {
    throw new ApiRequestError(response.status, "Oturum kapatılamadı.");
  }
}

export async function fetchCurrentUser(): Promise<CurrentUser | null> {
  let response: Response;
  try {
    response = await fetch("/api/v1/auth/me", { credentials: "include" });
  } catch {
    throw new ApiRequestError(0, "Sunucuya ulaşılamadı.");
  }
  if (response.status === 401) {
    return null;
  }
  const payload: unknown = await response.json();
  if (!response.ok) {
    throw new ApiRequestError(response.status, messageFrom(payload));
  }
  return readUser(payload);
}

function readMessage(payload: unknown): string {
  if (!isRecord(payload) || typeof payload.message !== "string") {
    throw new ApiRequestError(500, "Yanıt okunamadı.");
  }
  return payload.message;
}

function readUser(payload: unknown): CurrentUser {
  const text = ["id", "first_name", "last_name", "email", "member_since", "role"] as const;
  const company = ["company_id", "company_name", "company_slug", "company_timezone"] as const;
  const staffOnly = isRecord(payload) && payload.staff_only === true;
  if (
    !isRecord(payload) ||
    text.some((key) => typeof payload[key] !== "string") ||
    (!staffOnly && company.some((key) => typeof payload[key] !== "string")) ||
    typeof payload.setup_completed !== "boolean"
  ) {
    throw new ApiRequestError(500, "Hesap yanıtı okunamadı.");
  }
  return {
    id: String(payload.id),
    first_name: String(payload.first_name),
    last_name: String(payload.last_name),
    email: String(payload.email),
    member_since: String(payload.member_since),
    role: String(payload.role),
    company_id: String(payload.company_id ?? ""),
    company_name: String(payload.company_name ?? ""),
    company_slug: String(payload.company_slug ?? ""),
    company_timezone: String(payload.company_timezone ?? "Europe/Istanbul"),
    setup_completed: payload.setup_completed,
    is_platform_admin: payload.is_platform_admin === true,
    staff_only: staffOnly,
    closure_scheduled_for: typeof payload.closure_scheduled_for === "string" ? payload.closure_scheduled_for : null,
  };
}
