import { ApiRequestError, getJson, isRecord, postJson, sendJson } from "./http.ts";

export type Insight = {
  key: string;
  kind: string;
  module: string;
  severity: "high" | "medium" | "low";
  title: string;
  detail: string;
  link: string;
  task_id: string | null;
  task_assignee: string | null;
};

export type InsightList = { items: Insight[]; autopilot: boolean };
export type AutopilotKind = { key: string; module: string; label: string; on: boolean };
export type Autopilot = { enabled: boolean; default_assignee_id: string | null; kinds: AutopilotKind[]; last_run_at: string | null };

export async function fetchInsights(): Promise<InsightList> {
  const payload = await getJson("/api/v1/insights");
  if (!isRecord(payload) || !Array.isArray(payload.items)) throw new ApiRequestError(500, "Uyarılar okunamadı.");
  return payload as InsightList;
}

export async function fetchAutopilot(): Promise<Autopilot> {
  const payload = await getJson("/api/v1/autopilot");
  if (!isRecord(payload) || !Array.isArray(payload.kinds)) throw new ApiRequestError(500, "Otomatik görev ayarları okunamadı.");
  return payload as Autopilot;
}

export async function saveAutopilot(settings: { enabled: boolean; kinds: string[]; default_assignee_id: string | null }): Promise<Autopilot> {
  return (await sendJson("PUT", "/api/v1/autopilot", settings)) as Autopilot;
}

export async function runAutopilot(): Promise<{ created: number; resolved: number }> {
  return (await postJson("/api/v1/autopilot/run", undefined)) as { created: number; resolved: number };
}
