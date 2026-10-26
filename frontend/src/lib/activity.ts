import { ApiRequestError, getJson, isRecord } from "./http.ts";
import type { ModuleKey } from "./modules.ts";

export type ActivityModule = ModuleKey | "workspace";

export type ActivityItem = {
  id: string;
  module: ActivityModule;
  action: string;
  actor_id: string | null;
  actor_name: string;
  verb: string;
  target: string | null;
  detail: string | null;
  link: string | null;
  created_at: string;
};

export type ActivityPage = { items: ActivityItem[]; next_cursor: string | null; actors: { id: string; name: string }[] };

export type ActivityQuery = { module?: string; actor?: string; cursor?: string; limit?: number };

export async function fetchActivity(query: ActivityQuery = {}): Promise<ActivityPage> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const payload = await getJson(`/api/v1/activity${params.size ? `?${params}` : ""}`);
  if (!isRecord(payload) || !Array.isArray(payload.items) || !Array.isArray(payload.actors)) throw new ApiRequestError(500, "Etkinlikler okunamadı.");
  return payload as ActivityPage;
}

const dayFormat = new Intl.DateTimeFormat("tr-TR", { weekday: "long", day: "numeric", month: "long" });
const yearFormat = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "long", year: "numeric" });
const timeFormat = new Intl.DateTimeFormat("tr-TR", { hour: "2-digit", minute: "2-digit" });

export function activityDay(iso: string, now: Date): string {
  const date = new Date(iso);
  const start = (value: Date) => new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
  const diff = Math.round((start(now) - start(date)) / 86_400_000);
  if (diff === 0) return "Bugün";
  if (diff === 1) return "Dün";
  return date.getFullYear() === now.getFullYear() ? dayFormat.format(date) : yearFormat.format(date);
}

export function activityTime(iso: string): string {
  return timeFormat.format(new Date(iso));
}
