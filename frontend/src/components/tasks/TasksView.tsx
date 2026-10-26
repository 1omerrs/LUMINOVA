import { useEffect, useState, type DragEvent } from "react";
import { useSearchParams } from "react-router";
import { ApiRequestError } from "../../lib/http.ts";
import { readOnly, type WorkspaceModule } from "../../lib/modules.ts";
import { fetchProjects } from "../../lib/projects.ts";
import {
  deleteTask,
  dueLabels,
  dueText,
  fetchAssignees,
  fetchTask,
  fetchTasks,
  fetchTaskSummary,
  initialsOf,
  moveTask,
  priorities,
  priorityLabels,
  priorityTone,
  statuses,
  statusLabels,
  type Assignee,
  type Task,
  type TaskDue,
  type TaskPriority,
  type TaskStatus,
  type TaskSummary,
} from "../../lib/tasks.ts";
import { useWorkspace } from "../../lib/workspace.ts";
import { Alert, Button, Spinner } from "../forms/Controls.tsx";
import { ConfirmDialog } from "../ui/ConfirmDialog.tsx";
import { Icon } from "../ui/Icon.tsx";
import { ModuleIcon } from "../workspace/ModuleIcon.tsx";
import { fetchCustomer } from "../../lib/customers.ts";
import { QuickAdd } from "./QuickAdd.tsx";
import { TaskEditor } from "./TaskEditor.tsx";
import { AutopilotSheet } from "./AutopilotSheet.tsx";
import { TemplatesSheet } from "./TemplatesSheet.tsx";
import { TodayBoard } from "./TodayBoard.tsx";

const DONE_LIMIT = 20;
const OPEN_LIMIT = 100;
const columnDot: Record<TaskStatus, string> = { todo: "bg-slate/50", in_progress: "bg-violet", done: "bg-success" };
const emptyText: Record<TaskStatus, string> = {
  todo: "Yapılacak görev yok.",
  in_progress: "Üzerinde çalışılan görev yok. Bir görevi buraya sürükleyin veya “Başla” deyin.",
  done: "Henüz tamamlanan görev yok.",
};
const filterSelect =
  "h-10 rounded-lg border border-mist bg-surface px-3 text-[14px] text-graphite outline-none hover:border-stone focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)]";

type Column = { items: Task[]; total: number };
type Board = { columns: Record<TaskStatus, Column>; today: string };
type Load = { status: "loading" } | { status: "ready"; board: Board } | { status: "failed"; message: string };

export function TasksView({ module }: { module: WorkspaceModule }) {
  const { refreshFeed, modules, user } = useWorkspace();
  const projectsOn = modules.some((item) => item.key === "projects" && item.enabled);
  const customersOn = modules.some((item) => item.key === "customers" && item.enabled);
  const [params, setParams] = useSearchParams();
  const assignee = params.get("sorumlu");
  const project = params.get("proje");
  const customer = params.get("musteri");
  const view = params.get("gorunum") ?? (assignee || project || customer ? "pano" : "bugun");
  const [customerName, setCustomerName] = useState<{ id: string; name: string } | null>(null);
  const [templates, setTemplates] = useState(false);
  const [autopilot, setAutopilot] = useState(false);
  const [projects, setProjects] = useState<{ id: string; name: string }[]>([]);
  const [input, setInput] = useState("");
  const [search, setSearch] = useState("");
  const [priority, setPriority] = useState<TaskPriority | null>(null);
  const [due, setDue] = useState<TaskDue | null>(null);
  const [reload, setReload] = useState(0);
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [summary, setSummary] = useState<TaskSummary | null>(null);
  const [assignees, setAssignees] = useState<Assignee[]>([]);
  const [editing, setEditing] = useState<{ task: Task | null; status?: TaskStatus } | null>(null);
  const [deleting, setDeleting] = useState<Task | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState<Task | null>(null);
  const [dropTarget, setDropTarget] = useState<TaskStatus | null>(null);

  useEffect(() => {
    const next = input.trim();
    if (next === search) return;
    const timer = window.setTimeout(() => setSearch(next), 300);
    return () => window.clearTimeout(timer);
  }, [input, search]);

  useEffect(() => {
    let cancelled = false;
    fetchAssignees()
      .then((people) => {
        if (!cancelled) setAssignees(people);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!projectsOn) return;
    let cancelled = false;
    fetchProjects({ sort: "name", pageSize: 100 })
      .then((page) => {
        if (!cancelled) setProjects(page.items.map((item) => ({ id: item.id, name: item.name })));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [projectsOn]);

  const focusTask = params.get("gorev");
  useEffect(() => {
    if (!focusTask) return;
    let cancelled = false;
    const clear = () =>
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          next.delete("gorev");
          return next;
        },
        { replace: true },
      );
    fetchTask(focusTask)
      .then((found) => {
        if (cancelled) return;
        setEditing({ task: found });
        clear();
      })
      .catch(() => {
        if (!cancelled) clear();
      });
    return () => {
      cancelled = true;
    };
  }, [focusTask, setParams]);

  useEffect(() => {
    if (!customer || !customersOn) return;
    let cancelled = false;
    fetchCustomer(customer)
      .then((found) => {
        if (!cancelled) setCustomerName({ id: found.id, name: found.name });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [customer, customersOn]);

  useEffect(() => {
    let cancelled = false;
    const filters = { q: search, priority, assignee, due, project, customer };
    Promise.all([
      fetchTasks({ ...filters, status: "todo", sort: "due_date", pageSize: OPEN_LIMIT }),
      fetchTasks({ ...filters, status: "in_progress", sort: "due_date", pageSize: OPEN_LIMIT }),
      fetchTasks({ ...filters, status: "done", sort: "-completed_at", pageSize: DONE_LIMIT }),
      fetchTaskSummary(),
    ])
      .then(([todo, progress, done, totals]) => {
        if (cancelled) return;
        setLoad({
          status: "ready",
          board: {
            today: totals.today,
            columns: {
              todo: { items: todo.items, total: todo.total },
              in_progress: { items: progress.items, total: progress.total },
              done: { items: done.items, total: done.total },
            },
          },
        });
        setSummary(totals);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setLoad({ status: "failed", message: caught instanceof ApiRequestError ? caught.message : "Görevler yüklenemedi." });
      });
    return () => {
      cancelled = true;
    };
  }, [search, priority, assignee, due, project, customer, reload]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 4000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const board = load.status === "ready" ? load.board : null;
  const filtered = Boolean(search || priority || assignee || due || project || customer);
  const me = assignees.find((person) => person.me) ?? null;
  const activeCustomer = customer && customerName?.id === customer ? { id: customer, label: customerName.name } : null;

  function setParam(key: "sorumlu" | "proje" | "musteri" | "gorunum", value: string | null) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  function clearFilters() {
    setInput("");
    setSearch("");
    setPriority(null);
    setDue(null);
    setParams({}, { replace: true });
  }

  async function move(task: Task, status: TaskStatus) {
    if (task.status === status || !board) return;
    setError("");
    const columns = { ...board.columns };
    columns[task.status] = { items: columns[task.status].items.filter((item) => item.id !== task.id), total: columns[task.status].total - 1 };
    columns[status] = { items: [{ ...task, status, overdue: status === "done" ? false : task.overdue }, ...columns[status].items], total: columns[status].total + 1 };
    setLoad({ status: "ready", board: { ...board, columns } });
    try {
      await moveTask(task.id, status);
      setNotice(`“${task.title}” ${statusLabels[status].toLocaleLowerCase("tr")} olarak işaretlendi.`);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Görev taşınamadı.");
    }
    setReload((value) => value + 1);
  }

  function onDrop(event: DragEvent<HTMLElement>, status: TaskStatus) {
    event.preventDefault();
    setDropTarget(null);
    if (dragging) void move(dragging, status);
    setDragging(null);
  }

  const hasTasks = summary ? summary.todo + summary.in_progress + summary.done > 0 : false;

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-4">
          <div className="min-w-0">
            <h1 className="font-display text-[22px] font-semibold tracking-[-0.02em] text-midnight sm:text-[24px]">{module.name}</h1>
            <p className="mt-0.5 text-[14px] text-slate">
              {summary && hasTasks ? (
                <>
                  {summary.todo + summary.in_progress} açık görev
                  {summary.overdue > 0 ? (
                    <>
                      {" · "}
                      <span className="font-medium text-error-text">{summary.overdue} gecikmiş</span>
                    </>
                  ) : null}
                  {summary.due_today > 0 ? ` · ${summary.due_today} bugün teslim` : ""}
                </>
              ) : (
                module.summary
              )}
            </p>
          </div>
        </div>
        {readOnly(module) ? null : (
          <div className="flex gap-2">
            <Button size="lg" variant="quiet" onClick={() => setAutopilot(true)}>
              <Icon name="activity" className="h-4 w-4" />
              Otomatik
            </Button>
            <Button size="lg" variant="quiet" onClick={() => setTemplates(true)}>
              Şablonlar
            </Button>
            <Button size="lg" onClick={() => setEditing({ task: null })}>
              <Icon name="plus" className="h-4 w-4" strokeWidth={2} />
              Yeni görev
            </Button>
          </div>
        )}
      </section>

      <nav aria-label="Görünüm" className="flex items-center gap-5 border-b border-hairline">
        {[
          { key: "bugun", label: "Bugün" },
          { key: "pano", label: "Pano" },
        ].map((tab) => (
          <button
            key={tab.key}
            type="button"
            aria-current={view === tab.key ? "page" : undefined}
            onClick={() => setParam("gorunum", tab.key)}
            className={`-mb-px border-b-2 pb-2.5 text-[13.5px] font-medium transition-colors ${
              view === tab.key ? "border-midnight text-midnight" : "border-transparent text-slate hover:text-graphite"
            }`}
          >
            {tab.label}
          </button>
        ))}
        {activeCustomer ? (
          <span className="mb-2 ml-auto inline-flex items-center gap-1.5 rounded-md bg-paper py-1 pl-2.5 pr-1 text-[12.5px] ring-1 ring-inset ring-mist">
            Müşteri: <span className="font-medium">{activeCustomer.label}</span>
            <button type="button" aria-label="Müşteri filtresini kaldır" onClick={() => setParam("musteri", null)} className="grid h-5 w-5 place-items-center rounded text-slate hover:bg-mist/60">
              <Icon name="close" className="h-3 w-3" />
            </button>
          </span>
        ) : null}
      </nav>

      {notice ? <Alert tone="success">{notice}</Alert> : null}
      {error ? <Alert tone="error">{error}</Alert> : null}

      {view === "bugun" ? (
        <TodayBoard
          version={reload}
          onOpen={(task) => setEditing({ task })}
          onChanged={(message) => {
            setNotice(message);
            setReload((value) => value + 1);
          }}
        />
      ) : null}

      <section aria-label="Görev filtreleri" style={view === "bugun" ? { display: "none" } : undefined} className="flex flex-col gap-3 rounded-2xl border border-mist/80 bg-surface px-4 py-3 sm:px-5 xl:flex-row xl:items-center">
        <label className="relative block w-full xl:w-72">
          <span className="sr-only">Görev ara</span>
          <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate" />
          <input
            type="search"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Başlık veya açıklamada ara"
            className="h-10 w-full rounded-lg border border-mist bg-surface pl-9 pr-3 text-[14px] outline-none placeholder:text-slate/70 hover:border-stone focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)]"
          />
        </label>
        <div className="grid grid-cols-2 gap-3 sm:flex sm:items-center">
          <select aria-label="Sorumlu" value={assignee ?? ""} onChange={(event) => setParam("sorumlu", event.target.value || null)} className={filterSelect}>
            <option value="">Herkes</option>
            <option value="me">Bana atananlar</option>
            <option value="none">Atanmamış</option>
            {assignees
              .filter((person) => !person.me)
              .map((person) => (
                <option key={person.id} value={person.id}>
                  {person.name}
                </option>
              ))}
          </select>
          <select aria-label="Öncelik" value={priority ?? ""} onChange={(event) => setPriority((event.target.value || null) as TaskPriority | null)} className={filterSelect}>
            <option value="">Tüm öncelikler</option>
            {priorities.map((item) => (
              <option key={item} value={item}>
                {priorityLabels[item]}
              </option>
            ))}
          </select>
          {projectsOn ? (
            <select aria-label="Proje" value={project ?? ""} onChange={(event) => setParam("proje", event.target.value || null)} className={`${filterSelect} col-span-2 sm:col-span-1 sm:max-w-[220px]`}>
              <option value="">Tüm projeler</option>
              <option value="none">Projesiz</option>
              {projects.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          ) : null}
        </div>
        <div role="group" aria-label="Teslim tarihi" className="flex flex-wrap gap-1 rounded-xl bg-cloud p-1">
          {([null, "overdue", "today", "week", "none"] as (TaskDue | null)[]).map((value) => (
            <button
              key={value ?? "all"}
              type="button"
              aria-pressed={due === value}
              onClick={() => setDue(value)}
              className={`h-8 shrink-0 rounded-[9px] px-3 text-[13px] font-semibold transition-colors ${
                due === value ? "bg-surface text-graphite shadow-[0_1px_3px_rgba(16,19,28,0.12)]" : "text-slate hover:text-graphite"
              }`}
            >
              {value ? dueLabels[value] : "Tüm tarihler"}
            </button>
          ))}
        </div>
        {filtered ? (
          <button type="button" onClick={clearFilters} className="text-[13px] font-semibold text-violet hover:underline xl:ml-auto">
            Filtreleri temizle
          </button>
        ) : null}
      </section>

      {view === "bugun" ? null : load.status === "failed" ? (
        <Alert tone="error">
          {load.message}{" "}
          <button type="button" onClick={() => setReload((value) => value + 1)} className="font-semibold underline">
            Tekrar dene
          </button>
        </Alert>
      ) : !board ? (
        <p role="status" className="flex items-center gap-2.5 py-12 text-[14px] text-slate">
          <Spinner className="h-4 w-4 text-violet" /> Görevler yükleniyor.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {statuses.map((status) => {
            const column = board.columns[status];
            const target = dropTarget === status && dragging?.status !== status;
            return (
              <section
                key={status}
                aria-labelledby={`column-${status}`}
                onDragOver={(event) => {
                  if (!dragging) return;
                  event.preventDefault();
                  event.dataTransfer.dropEffect = "move";
                  if (dropTarget !== status) setDropTarget(status);
                }}
                onDragLeave={(event) => {
                  if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDropTarget(null);
                }}
                onDrop={(event) => onDrop(event, status)}
                className={`flex min-w-0 flex-col rounded-2xl border bg-white/70 transition-colors ${
                  target ? "border-violet/50 bg-violet/[0.04] shadow-[0_0_0_4px_rgba(91,71,214,0.10)]" : "border-mist/80"
                }`}
              >
                <header className="flex items-center justify-between gap-3 px-4 pb-2 pt-4">
                  <h2 id={`column-${status}`} className="flex items-center gap-2 text-[14px] font-semibold">
                    <span aria-hidden className={`h-2 w-2 rounded-full ${columnDot[status]}`} />
                    {statusLabels[status]}
                  </h2>
                  <span className="rounded-full bg-cloud px-2 py-0.5 text-[12px] font-semibold tabular-nums text-slate">{column.total}</span>
                </header>

                {status === "todo" ? (
                  <QuickAdd
                    assigneeId={me?.id ?? null}
                    projectId={project && project !== "none" ? project : null}
                    onCreated={(task) => {
                      setNotice(`“${task.title}” eklendi.`);
                      setReload((value) => value + 1);
                    }}
                  />
                ) : null}

                <ul className="flex flex-1 flex-col gap-2 px-3 pb-3 pt-1">
                  {column.items.length === 0 ? (
                    <li className="rounded-xl border border-dashed border-mist px-4 py-6 text-center text-[13px] leading-5 text-slate">
                      {filtered ? "Filtreyle eşleşen görev yok." : emptyText[status]}
                    </li>
                  ) : (
                    column.items.map((task) => (
                      <TaskCard
                        key={task.id}
                        task={task}
                        today={board.today}
                        dragging={dragging?.id === task.id}
                        onOpen={() => setEditing({ task })}
                        onMove={(next) => void move(task, next)}
                        onDragStart={() => setDragging(task)}
                        onDragEnd={() => {
                          setDragging(null);
                          setDropTarget(null);
                        }}
                      />
                    ))
                  )}
                  {column.total > column.items.length ? (
                    <li className="px-1 pt-1 text-[12px] text-slate">
                      {status === "done" ? `Son ${column.items.length} tamamlanan görev gösteriliyor.` : `İlk ${column.items.length} görev gösteriliyor; filtreleri daraltın.`}
                    </li>
                  ) : null}
                </ul>
              </section>
            );
          })}
        </div>
      )}

      {editing && board ? (
        <TaskEditor
          key={editing.task?.id ?? "new"}
          task={editing.task}
          initialStatus={editing.status}
          initialProject={project && project !== "none" ? project : null}
          assignees={assignees}
          projects={projectsOn ? projects : undefined}
          customersOn={customersOn}
          initialCustomer={activeCustomer}
          today={board.today}
          onClose={() => setEditing(null)}
          onSaved={(task, created) => {
            setEditing(null);
            setNotice(created ? `“${task.title}” eklendi.` : `“${task.title}” güncellendi.`);
            setReload((value) => value + 1);
            void refreshFeed();
          }}
          onDelete={(task) => {
            setEditing(null);
            setDeleting(task);
          }}
        />
      ) : null}

      {autopilot ? (
        <AutopilotSheet
          assignees={assignees}
          canEdit={user.role === "owner" || user.role === "admin"}
          enabledModules={new Set(modules.filter((item) => item.enabled).map((item) => item.key))}
          onClose={() => setAutopilot(false)}
          onSaved={(message) => {
            setAutopilot(false);
            setNotice(message);
            setReload((value) => value + 1);
            refreshFeed();
          }}
        />
      ) : null}

      {templates && board ? (
        <TemplatesSheet
          assignees={assignees}
          projects={projectsOn ? projects : undefined}
          customersOn={customersOn}
          today={board.today}
          onClose={() => setTemplates(false)}
          onApplied={(count, name) => {
            setTemplates(false);
            setNotice(`“${name}” şablonundan ${count} görev oluşturuldu.`);
            setReload((value) => value + 1);
          }}
        />
      ) : null}

      {deleting ? (
        <ConfirmDialog
          title="Görev silinsin mi?"
          confirmLabel="Görevi sil"
          pendingLabel="Siliniyor"
          onClose={() => setDeleting(null)}
          onConfirm={async () => {
            await deleteTask(deleting.id);
            setNotice(`“${deleting.title}” silindi.`);
            setDeleting(null);
            setReload((value) => value + 1);
          }}
        >
          “{deleting.title}” panodan kaldırılır. Kayıt denetim geçmişinde kalır.
        </ConfirmDialog>
      ) : null}
    </div>
  );
}

function TaskCard({
  task,
  today,
  dragging,
  onOpen,
  onMove,
  onDragStart,
  onDragEnd,
}: {
  task: Task;
  today: string;
  dragging: boolean;
  onOpen: () => void;
  onMove: (status: TaskStatus) => void;
  onDragStart: () => void;
  onDragEnd: () => void;
}) {
  const due = dueText(task, today);
  const done = task.status === "done";
  return (
    <li
      draggable
      onDragStart={(event) => {
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", task.id);
        onDragStart();
      }}
      onDragEnd={onDragEnd}
      className={`group rounded-xl border bg-surface p-3 shadow-[0_1px_2px_rgba(16,19,28,0.04)] transition-[box-shadow,opacity,border-color] hover:border-stone hover:shadow-[0_6px_16px_-10px_rgba(32,36,50,0.35)] ${
        dragging ? "opacity-40" : ""
      } ${task.overdue ? "border-error/30" : "border-mist/80"}`}
    >
      <div className="flex items-start gap-2.5">
        <button
          type="button"
          role="checkbox"
          aria-checked={done}
          aria-label={done ? `“${task.title}” görevini yeniden aç` : `“${task.title}” görevini tamamla`}
          onClick={() => onMove(done ? "todo" : "done")}
          className={`mt-0.5 grid h-[18px] w-[18px] shrink-0 place-items-center rounded-full border transition-colors ${
            done ? "border-success bg-success text-white" : "border-stone text-transparent hover:border-success hover:text-success"
          }`}
        >
          <Icon name="check" className="h-3 w-3" strokeWidth={2.6} />
        </button>
        <button type="button" onClick={onOpen} className="min-w-0 flex-1 text-left">
          <span className={`block text-[14px] font-medium leading-5 ${done ? "text-slate line-through decoration-slate/40" : "text-graphite"}`}>{task.title}</span>
          {task.description ? <span className="mt-0.5 line-clamp-2 block text-[12px] leading-[18px] text-slate">{task.description}</span> : null}
        </button>
      </div>
      <div className="mt-2.5 flex flex-wrap items-center gap-1.5 pl-[28px]">
        {task.priority !== "normal" ? (
          <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${priorityTone[task.priority]}`}>{priorityLabels[task.priority]}</span>
        ) : null}
        {due ? (
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
              due.tone === "late" ? "bg-error/[0.08] text-error-text" : due.tone === "soon" ? "bg-violet/10 text-violet" : "text-slate"
            }`}
          >
            <Icon name="calendar" className="h-3 w-3" />
            {due.text}
          </span>
        ) : null}
        {task.blocked ? (
          <span
            title={`Önce: ${task.depends_on.filter((dep) => dep.status !== "done").map((dep) => dep.title).join(", ")}`}
            className="inline-flex items-center gap-1 rounded-full bg-cloud px-2 py-0.5 text-[11px] font-semibold text-slate ring-1 ring-inset ring-mist"
          >
            <Icon name="lock" className="h-3 w-3" /> Bekliyor
          </span>
        ) : null}
        {task.automatic ? (
          <span title="LUMINOVA bu görevi kayıtlarınızdaki bir duruma göre açtı" className="rounded-full bg-violet/10 px-2 py-0.5 text-[11px] font-semibold text-violet">
            Otomatik
          </span>
        ) : null}
        {task.project_name ? (
          <span className="inline-flex min-w-0 max-w-[150px] items-center gap-1 text-[11px] font-medium text-slate">
            <ModuleIcon name="projects" className="h-3 w-3 shrink-0" />
            <span className="truncate">{task.project_name}</span>
          </span>
        ) : null}
        {task.customer_name ? (
          <span className="inline-flex min-w-0 max-w-[150px] items-center gap-1 text-[11px] font-medium text-slate">
            <ModuleIcon name="customers" className="h-3 w-3 shrink-0" />
            <span className="truncate">{task.customer_name}</span>
          </span>
        ) : null}
        {task.order_code ? <span className="text-[11px] font-medium tabular-nums text-slate">{task.order_code}</span> : null}
        <span className="ml-auto flex items-center gap-1.5">
          {task.status === "todo" && !task.blocked ? (
            <button
              type="button"
              onClick={() => onMove("in_progress")}
              aria-label={`“${task.title}” görevine başla`}
              className="h-6 rounded-md px-2 text-[11px] font-semibold text-slate transition-colors hover:bg-violet/[0.08] hover:text-violet group-hover:text-violet"
            >
              Başla
            </button>
          ) : null}
          {task.assignee_name ? (
            <span
              title={task.assignee_name}
              aria-label={`Sorumlu: ${task.assignee_name}`}
              className="grid h-6 w-6 place-items-center rounded-full bg-graphite text-[10px] font-semibold text-onink"
            >
              {initialsOf(task.assignee_name)}
            </span>
          ) : null}
        </span>
      </div>
    </li>
  );
}
