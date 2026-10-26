import { ApiRequestError, getJson, isRecord, postJson, sendJson } from "./http.ts";

export type ProjectStatus = "planned" | "active" | "on_hold" | "completed";
export type ProjectSort = "due_date" | "-created_at" | "name";

export type Project = {
  id: string;
  name: string;
  description: string | null;
  status: ProjectStatus;
  customer_id: string | null;
  customer_name: string | null;
  quote_id: string | null;
  quote_code: string | null;
  order_id: string | null;
  order_code: string | null;
  start_date: string | null;
  due_date: string | null;
  working_days_only: boolean;
  overdue: boolean;
  completed_at: string | null;
  task_total: number;
  task_done: number;
  task_overdue: number;
  progress: number;
  milestone_total: number;
  milestone_done: number;
  next_milestone: string | null;
  next_milestone_due: string | null;
  created_at: string;
  updated_at: string;
};

export type Milestone = {
  id: string;
  title: string;
  due_date: string | null;
  done: boolean;
  overdue: boolean;
  completed_at: string | null;
  position: number;
};

export type MilestonePayload = { title: string; due_date: string | null; done: boolean };

function readMilestones(payload: unknown): Milestone[] {
  if (!Array.isArray(payload)) throw new ApiRequestError(500, "Aşamalar okunamadı.");
  return payload as Milestone[];
}

export async function fetchMilestones(projectId: string): Promise<Milestone[]> {
  return readMilestones(await getJson(`/api/v1/projects/${projectId}/milestones`));
}

export async function addMilestone(projectId: string, payload: MilestonePayload): Promise<Milestone[]> {
  return readMilestones(await postJson(`/api/v1/projects/${projectId}/milestones`, payload));
}

export async function updateMilestone(projectId: string, id: string, payload: MilestonePayload): Promise<Milestone[]> {
  return readMilestones(await sendJson("PUT", `/api/v1/projects/${projectId}/milestones/${id}`, payload));
}

export async function moveMilestone(projectId: string, id: string, direction: "up" | "down"): Promise<Milestone[]> {
  return readMilestones(await postJson(`/api/v1/projects/${projectId}/milestones/${id}/move`, { direction }));
}

export async function deleteMilestone(projectId: string, id: string): Promise<Milestone[]> {
  return readMilestones(await sendJson("DELETE", `/api/v1/projects/${projectId}/milestones/${id}`));
}

export type ProjectPage = { items: Project[]; total: number; page: number; page_size: number; today: string };
export type ProjectSummary = Record<ProjectStatus, number> & { overdue: number };
export type ProjectPayload = {
  name: string;
  description: string;
  status: ProjectStatus;
  customer_id: string | null;
  quote_id?: string | null;
  order_id?: string | null;
  template_id?: string | null;
  start_date: string | null;
  due_date: string | null;
  working_days_only: boolean;
};

export const projectStatuses: ProjectStatus[] = ["planned", "active", "on_hold", "completed"];
export const projectStatusLabels: Record<ProjectStatus, string> = {
  planned: "Planlandı",
  active: "Devam ediyor",
  on_hold: "Beklemede",
  completed: "Tamamlandı",
};
export const projectStatusTone: Record<ProjectStatus, string> = {
  planned: "bg-cloud text-slate ring-1 ring-inset ring-mist",
  active: "bg-violet/10 text-violet",
  on_hold: "bg-warning/10 text-warning-text",
  completed: "bg-success/10 text-success-text",
};
export const projectSortLabels: Record<ProjectSort, string> = {
  due_date: "Teslim tarihi",
  "-created_at": "En yeni",
  name: "Ada göre (A–Z)",
};

export async function fetchProjects(options: { q?: string; status?: ProjectStatus | null; sort?: ProjectSort; page?: number; pageSize?: number }): Promise<ProjectPage> {
  const params = new URLSearchParams();
  if (options.q) params.set("q", options.q);
  if (options.status) params.set("status", options.status);
  if (options.sort) params.set("sort", options.sort);
  if (options.page) params.set("page", String(options.page));
  if (options.pageSize) params.set("page_size", String(options.pageSize));
  const payload = await getJson(`/api/v1/projects?${params.toString()}`);
  if (!isRecord(payload) || !Array.isArray(payload.items) || typeof payload.total !== "number" || typeof payload.today !== "string") {
    throw new ApiRequestError(500, "Proje listesi okunamadı.");
  }
  return payload as ProjectPage;
}

export async function fetchProjectSummary(): Promise<ProjectSummary> {
  const payload = await getJson("/api/v1/projects/summary");
  if (!isRecord(payload) || typeof payload.active !== "number") throw new ApiRequestError(500, "Proje özeti okunamadı.");
  return payload as ProjectSummary;
}

export async function fetchProject(id: string): Promise<Project> {
  return readProject(await getJson(`/api/v1/projects/${id}`));
}

export async function createProject(payload: ProjectPayload): Promise<Project> {
  return readProject(await postJson("/api/v1/projects", payload));
}

export async function updateProject(id: string, payload: ProjectPayload): Promise<Project> {
  return readProject(await sendJson("PUT", `/api/v1/projects/${id}`, payload));
}

export async function deleteProject(id: string): Promise<void> {
  await sendJson("DELETE", `/api/v1/projects/${id}`);
}

export type TemplateTask = {
  stage: string;
  title: string;
  description: string | null;
  priority: "low" | "normal" | "high" | "urgent";
  duration_days: number;
  depends_on: number[];
};

export type ProjectTemplate = {
  id: string;
  name: string;
  description: string | null;
  items: TemplateTask[];
  stages: string[];
  total_days: number;
  created_at: string;
  updated_at: string;
};

export type PlanTask = {
  id: string;
  title: string;
  status: "todo" | "in_progress" | "done";
  priority: "low" | "normal" | "high" | "urgent";
  start_date: string | null;
  due_date: string | null;
  duration_days: number | null;
  milestone_id: string | null;
  depends_on: string[];
  assignee_name: string | null;
  blocked: boolean;
  overdue: boolean;
  critical: boolean;
};

export type RiskKind = "late_finish" | "behind" | "overdue_task" | "bottleneck" | "unassigned" | "late_milestone" | "no_plan";
export type PlanRisk = { kind: RiskKind; severity: "high" | "medium" | "low"; title: string; detail: string; task_id: string | null };

export type ProjectPlan = {
  today: string;
  tasks: PlanTask[];
  milestones: Milestone[];
  actual_progress: number;
  expected_progress: number | null;
  projected_finish: string | null;
  delay_days: number;
  risks: PlanRisk[];
  pending_changes: number;
};

export type ScheduleChange = { task_id: string; title: string; old_start: string | null; old_due: string | null; new_start: string; new_due: string };
export type RescheduleResult = { changes: ScheduleChange[]; projected_finish: string | null; delay_days: number; applied: boolean };

export async function fetchProjectTemplates(): Promise<ProjectTemplate[]> {
  const payload = await getJson("/api/v1/projects/templates");
  if (!Array.isArray(payload)) throw new ApiRequestError(500, "Proje şablonları okunamadı.");
  return payload as ProjectTemplate[];
}

export async function saveProjectTemplate(payload: { name: string; description: string | null; items: TemplateTask[] }, id?: string): Promise<ProjectTemplate> {
  return (await (id ? sendJson("PUT", `/api/v1/projects/templates/${id}`, payload) : postJson("/api/v1/projects/templates", payload))) as ProjectTemplate;
}

export async function deleteProjectTemplate(id: string): Promise<void> {
  await sendJson("DELETE", `/api/v1/projects/templates/${id}`);
}

export async function fetchPlan(projectId: string): Promise<ProjectPlan> {
  const payload = await getJson(`/api/v1/projects/${projectId}/plan`);
  if (!isRecord(payload) || !Array.isArray(payload.tasks) || !Array.isArray(payload.risks)) throw new ApiRequestError(500, "Proje planı okunamadı.");
  return payload as ProjectPlan;
}

export async function reschedule(projectId: string, apply: boolean): Promise<RescheduleResult> {
  return (await postJson(`/api/v1/projects/${projectId}/reschedule`, { apply })) as RescheduleResult;
}

function readProject(payload: unknown): Project {
  if (!isRecord(payload) || typeof payload.id !== "string" || typeof payload.name !== "string") throw new ApiRequestError(500, "Proje okunamadı.");
  return payload as Project;
}
