import { ApiRequestError, getJson, isRecord, postJson, sendJson } from "./http.ts";

export type TaskStatus = "todo" | "in_progress" | "done";
export type TaskPriority = "low" | "normal" | "high" | "urgent";
export type TaskSort = "due_date" | "-priority" | "-created_at" | "-completed_at" | "title";
export type TaskDue = "overdue" | "today" | "week" | "none";

export type Task = {
  id: string;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  due_date: string | null;
  overdue: boolean;
  assignee_id: string | null;
  assignee_name: string | null;
  project_id: string | null;
  project_name: string | null;
  customer_id: string | null;
  customer_name: string | null;
  order_id: string | null;
  order_code: string | null;
  depends_on: TaskRef[];
  blocked: boolean;
  automatic?: boolean;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type TaskRef = { id: string; title: string; status: TaskStatus };
export type TemplateStep = { title: string; description: string | null; priority: TaskPriority; offset_days: number | null; depends_on: number[] };
export type TaskTemplate = { id: string; name: string; description: string | null; items: TemplateStep[]; created_at: string; updated_at: string };
export type TemplateApply = {
  start_date: string | null;
  assignee_id: string | null;
  customer_id: string | null;
  order_id: string | null;
  project_id: string | null;
  once_per_record: boolean;
};
export type AssigneeLoad = { assignee_id: string | null; name: string; open: number; overdue: number; this_week: number };
export type TodayView = {
  today: string;
  overdue: Task[];
  due_today: Task[];
  in_progress: Task[];
  upcoming: Task[];
  waiting: Task[];
  unblocked: Task[];
  load: AssigneeLoad[];
};

export type TaskPage = { items: Task[]; total: number; page: number; page_size: number; today: string };
export type TaskSummary = { todo: number; in_progress: number; done: number; overdue: number; due_today: number; today: string };
export type Assignee = { id: string; name: string; me: boolean };
export type TaskPayload = {
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  due_date: string | null;
  assignee_id: string | null;
  project_id: string | null;
  customer_id?: string | null;
  order_id?: string | null;
};
export type TaskFilters = {
  q?: string;
  priority?: TaskPriority | null;
  assignee?: string | null;
  due?: TaskDue | null;
  project?: string | null;
  customer?: string | null;
  order?: string | null;
};

export const statuses: TaskStatus[] = ["todo", "in_progress", "done"];
export const priorities: TaskPriority[] = ["urgent", "high", "normal", "low"];

export const statusLabels: Record<TaskStatus, string> = { todo: "Yapılacak", in_progress: "Devam ediyor", done: "Tamamlandı" };
export const priorityLabels: Record<TaskPriority, string> = { urgent: "Acil", high: "Yüksek", normal: "Normal", low: "Düşük" };
export const priorityTone: Record<TaskPriority, string> = {
  urgent: "bg-error/[0.08] text-error-text",
  high: "bg-warning/10 text-warning-text",
  normal: "bg-cloud text-slate ring-1 ring-inset ring-mist",
  low: "bg-cloud text-slate/80",
};
export const dueLabels: Record<TaskDue, string> = { overdue: "Gecikenler", today: "Bugün", week: "Bu hafta", none: "Tarihsiz" };

const dayMs = 86_400_000;
const weekday = new Intl.DateTimeFormat("tr-TR", { weekday: "long", timeZone: "UTC" });
const shortDate = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "short", timeZone: "UTC" });
const longDate = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

function utc(iso: string): number {
  const [year, month, day] = iso.split("-").map(Number);
  return Date.UTC(year, month - 1, day);
}

export function dueText(task: Pick<Task, "due_date" | "status">, today: string): { text: string; tone: "late" | "soon" | "plain" } | null {
  if (!task.due_date) return null;
  const days = Math.round((utc(task.due_date) - utc(today)) / dayMs);
  const date = new Date(utc(task.due_date));
  const label = task.due_date.slice(0, 4) === today.slice(0, 4) ? shortDate.format(date) : longDate.format(date);
  if (task.status === "done") return { text: label, tone: "plain" };
  if (days < 0) return { text: `${-days} gün gecikti`, tone: "late" };
  if (days === 0) return { text: "Bugün", tone: "soon" };
  if (days === 1) return { text: "Yarın", tone: "soon" };
  if (days < 7) return { text: weekday.format(date), tone: "plain" };
  return { text: label, tone: "plain" };
}

export function initialsOf(name: string): string {
  const parts = name.split(" ").filter(Boolean);
  const first = parts[0]?.charAt(0) ?? "";
  const last = parts.length > 1 ? parts[parts.length - 1].charAt(0) : "";
  return `${first}${last}`.toLocaleUpperCase("tr");
}

export function addDays(iso: string, days: number): string {
  return new Date(utc(iso) + days * dayMs).toISOString().slice(0, 10);
}

export function formatDay(iso: string): string {
  return longDate.format(new Date(utc(iso)));
}

export async function fetchTasks(options: TaskFilters & { status?: TaskStatus; sort?: TaskSort; pageSize?: number }): Promise<TaskPage> {
  const params = new URLSearchParams();
  if (options.q) params.set("q", options.q);
  if (options.status) params.set("status", options.status);
  if (options.priority) params.set("priority", options.priority);
  if (options.assignee) params.set("assignee", options.assignee);
  if (options.due) params.set("due", options.due);
  if (options.project) params.set("project", options.project);
  if (options.customer) params.set("customer", options.customer);
  if (options.order) params.set("order", options.order);
  if (options.sort) params.set("sort", options.sort);
  if (options.pageSize) params.set("page_size", String(options.pageSize));
  const payload = await getJson(`/api/v1/tasks?${params.toString()}`);
  if (!isRecord(payload) || !Array.isArray(payload.items) || typeof payload.total !== "number" || typeof payload.today !== "string") {
    throw new ApiRequestError(500, "Görev listesi okunamadı.");
  }
  return payload as TaskPage;
}

export async function fetchTaskSummary(): Promise<TaskSummary> {
  const payload = await getJson("/api/v1/tasks/summary");
  if (!isRecord(payload) || typeof payload.todo !== "number") throw new ApiRequestError(500, "Görev özeti okunamadı.");
  return payload as TaskSummary;
}

export async function fetchAssignees(): Promise<Assignee[]> {
  const payload = await getJson("/api/v1/tasks/assignees");
  if (!Array.isArray(payload)) throw new ApiRequestError(500, "Sorumlu listesi okunamadı.");
  return payload as Assignee[];
}

export async function fetchTask(id: string): Promise<Task> {
  return readTask(await getJson(`/api/v1/tasks/${id}`));
}

export async function createTask(payload: TaskPayload): Promise<Task> {
  return readTask(await postJson("/api/v1/tasks", payload));
}

export async function updateTask(id: string, payload: TaskPayload): Promise<Task> {
  return readTask(await sendJson("PUT", `/api/v1/tasks/${id}`, payload));
}

export async function moveTask(id: string, status: TaskStatus): Promise<Task> {
  return readTask(await postJson(`/api/v1/tasks/${id}/status`, { status }));
}

export async function deleteTask(id: string): Promise<void> {
  await sendJson("DELETE", `/api/v1/tasks/${id}`);
}

export async function setDependencies(id: string, dependsOn: string[]): Promise<Task> {
  return readTask(await sendJson("PUT", `/api/v1/tasks/${id}/dependencies`, { depends_on: dependsOn }));
}

export async function fetchToday(): Promise<TodayView> {
  const payload = await getJson("/api/v1/tasks/today");
  if (!isRecord(payload) || !Array.isArray(payload.overdue)) throw new ApiRequestError(500, "Günlük görünüm okunamadı.");
  return payload as TodayView;
}

export async function fetchTemplates(): Promise<TaskTemplate[]> {
  const payload = await getJson("/api/v1/tasks/templates");
  if (!Array.isArray(payload)) throw new ApiRequestError(500, "Şablonlar okunamadı.");
  return payload as TaskTemplate[];
}

export async function saveTemplate(template: { name: string; description: string | null; items: TemplateStep[] }, id?: string): Promise<TaskTemplate> {
  return (await sendJson(id ? "PUT" : "POST", id ? `/api/v1/tasks/templates/${id}` : "/api/v1/tasks/templates", template)) as TaskTemplate;
}

export async function deleteTemplate(id: string): Promise<void> {
  await sendJson("DELETE", `/api/v1/tasks/templates/${id}`);
}

export async function applyTemplate(id: string, payload: TemplateApply): Promise<Task[]> {
  const result = await postJson(`/api/v1/tasks/templates/${id}/apply`, payload);
  if (!isRecord(result) || !Array.isArray(result.created)) throw new ApiRequestError(500, "Şablon uygulanamadı.");
  return result.created as Task[];
}

function readTask(payload: unknown): Task {
  if (!isRecord(payload) || typeof payload.id !== "string" || typeof payload.title !== "string") throw new ApiRequestError(500, "Görev okunamadı.");
  return payload as Task;
}
