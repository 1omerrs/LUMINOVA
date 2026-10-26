import { useEffect, useState } from "react";
import { Link } from "react-router";
import { ApiRequestError } from "../../lib/http.ts";
import { fetchPlan, fetchProject, projectStatusLabels, projectStatusTone, type Project, type ProjectPlan } from "../../lib/projects.ts";
import { dueText, fetchTasks, formatDay, initialsOf, moveTask, statusLabels, type Task } from "../../lib/tasks.ts";
import { Alert, Button, Spinner } from "../forms/Controls.tsx";
import { QuickAdd } from "../tasks/QuickAdd.tsx";
import { Icon } from "../ui/Icon.tsx";
import { Sheet } from "../ui/Sheet.tsx";
import { Milestones } from "./Milestones.tsx";
import { PlanProgress, RescheduleStrip, Risks, Timeline } from "./ProjectPlan.tsx";

type Load = { status: "loading" } | { status: "ready"; project: Project; tasks: Task[]; plan: ProjectPlan; today: string } | { status: "failed"; message: string };
type Tab = "overview" | "timeline" | "risks";

export function ProjectSheet({
  projectId,
  assigneeId,
  onClose,
  onEdit,
  onDelete,
  onChanged,
}: {
  projectId: string;
  assigneeId: string | null;
  onClose: () => void;
  onEdit: (project: Project) => void;
  onDelete: (project: Project) => void;
  onChanged: () => void;
}) {
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [reload, setReload] = useState(0);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("overview");

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchProject(projectId), fetchTasks({ project: projectId, sort: "due_date", pageSize: 100 }), fetchPlan(projectId)])
      .then(([project, page, plan]) => {
        if (!cancelled) setLoad({ status: "ready", project, tasks: page.items, plan, today: page.today });
      })
      .catch((caught: unknown) => {
        if (!cancelled) setLoad({ status: "failed", message: caught instanceof ApiRequestError ? caught.message : "Proje yüklenemedi." });
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, reload]);

  async function toggle(task: Task) {
    setError("");
    try {
      await moveTask(task.id, task.status === "done" ? "todo" : "done");
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Görev güncellenemedi.");
    }
    setReload((value) => value + 1);
    onChanged();
  }

  const ready = load.status === "ready" ? load : null;
  const project = ready?.project ?? null;
  const open = ready ? ready.tasks.filter((task) => task.status !== "done") : [];
  const done = ready ? ready.tasks.filter((task) => task.status === "done") : [];

  return (
    <Sheet
      wide
      title={project?.name ?? "Proje"}
      description={project ? (project.customer_name ?? "Müşteri bağlı değil") : undefined}
      onClose={onClose}
      footer={
        project ? (
          <>
            <Button variant="quiet" onClick={() => onDelete(project)} className="mr-auto text-error-text">
              <Icon name="trash" className="h-4 w-4" />
              Sil
            </Button>
            <Button variant="quiet" onClick={() => onEdit(project)}>
              <Icon name="pencil" className="h-4 w-4" />
              Düzenle
            </Button>
          </>
        ) : undefined
      }
    >
      {load.status === "failed" ? (
        <Alert tone="error">{load.message}</Alert>
      ) : !ready || !project ? (
        <p role="status" className="flex items-center gap-2.5 text-[14px] text-slate">
          <Spinner className="h-4 w-4 text-violet" /> Proje yükleniyor.
        </p>
      ) : (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-full px-2.5 py-1 text-[12px] font-semibold ${projectStatusTone[project.status]}`}>{projectStatusLabels[project.status]}</span>
            {project.start_date || project.due_date ? (
              <span className={`inline-flex items-center gap-1.5 text-[13px] ${project.overdue ? "font-medium text-error-text" : "text-slate"}`}>
                <Icon name="calendar" className="h-3.5 w-3.5" />
                {project.start_date ? formatDay(project.start_date) : "Başlangıç yok"} – {project.due_date ? formatDay(project.due_date) : "teslim tarihi yok"}
                {project.overdue ? " · teslim tarihi geçti" : ""}
              </span>
            ) : null}
            {project.quote_code ? (
              <Link to="/panel/musteriler?bolum=teklifler" className="rounded bg-cloud px-2 py-0.5 font-mono text-[11.5px] text-ink-soft ring-1 ring-inset ring-mist hover:text-violet">
                {project.quote_code}
              </Link>
            ) : null}
            {project.order_code ? (
              <Link to="/panel/satis" className="rounded bg-cloud px-2 py-0.5 font-mono text-[11.5px] text-ink-soft ring-1 ring-inset ring-mist hover:text-violet">
                {project.order_code}
              </Link>
            ) : null}
          </div>

          <div role="tablist" aria-label="Proje görünümü" className="flex gap-5 border-b border-hairline">
            {(
              [
                ["overview", "Genel"],
                ["timeline", "Zaman çizelgesi"],
                ["risks", ready.plan.risks.length ? `Riskler · ${ready.plan.risks.length}` : "Riskler"],
              ] as [Tab, string][]
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={tab === key}
                onClick={() => setTab(key)}
                className={`-mb-px border-b-2 pb-2.5 text-[13.5px] font-semibold transition-colors ${
                  tab === key ? "border-midnight text-midnight" : "border-transparent text-slate hover:text-graphite"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {ready.plan.pending_changes > 0 && project.status !== "completed" ? (
            <RescheduleStrip
              key={ready.plan.pending_changes}
              projectId={project.id}
              count={ready.plan.pending_changes}
              onApplied={() => {
                setReload((value) => value + 1);
                onChanged();
              }}
            />
          ) : null}

          {tab === "timeline" ? <Timeline project={project} plan={ready.plan} /> : null}
          {tab === "risks" ? <Risks plan={ready.plan} projectId={project.id} /> : null}
          {tab === "overview" ? (
            <>
              <PlanProgress project={project} plan={ready.plan} />
              {project.description ? <p className="whitespace-pre-line text-[14px] leading-6 text-graphite">{project.description}</p> : null}
              <Milestones key={reload} projectId={project.id} onChanged={onChanged} />
              <TaskList
                project={project}
                tasks={[...open, ...done]}
                today={ready.today}
                assigneeId={assigneeId}
                error={error}
                onToggle={(task) => void toggle(task)}
                onCreated={() => {
                  setReload((value) => value + 1);
                  onChanged();
                }}
              />
            </>
          ) : null}
        </div>
      )}
    </Sheet>
  );
}

function TaskList({
  project,
  tasks,
  today,
  assigneeId,
  error,
  onToggle,
  onCreated,
}: {
  project: Project;
  tasks: Task[];
  today: string;
  assigneeId: string | null;
  error: string;
  onToggle: (task: Task) => void;
  onCreated: () => void;
}) {
  return (
    <section aria-labelledby="project-tasks-title">
      <div className="flex items-center justify-between gap-3">
        <h3 id="project-tasks-title" className="text-[14px] font-semibold">
          Görevler
        </h3>
        <Link to={`/panel/gorevler?proje=${project.id}`} className="text-[13px] font-semibold text-violet hover:underline">
          Görev panosunda aç
        </Link>
      </div>
      <QuickAdd className="mt-3" assigneeId={assigneeId} projectId={project.id} onCreated={onCreated} />
      {error ? (
        <div className="mt-3">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}
      {tasks.length === 0 ? (
        <p className="mt-3 rounded-xl border border-dashed border-mist px-4 py-6 text-center text-[13px] text-slate">
          Bu projeye bağlı görev yok. Yukarıdan ekleyin; ilerleme tamamlanan görevlere göre hesaplanır.
        </p>
      ) : (
        <ul className="mt-3 divide-y divide-mist/60 overflow-hidden rounded-xl border border-mist/80">
          {tasks.map((task) => (
            <TaskRow key={task.id} task={task} today={today} onToggle={() => onToggle(task)} />
          ))}
        </ul>
      )}
    </section>
  );
}

function TaskRow({ task, today, onToggle }: { task: Task; today: string; onToggle: () => void }) {
  const done = task.status === "done";
  const due = dueText(task, today);
  return (
    <li className="flex items-center gap-3 bg-surface px-4 py-3">
      <button
        type="button"
        role="checkbox"
        aria-checked={done}
        aria-label={done ? `“${task.title}” görevini yeniden aç` : `“${task.title}” görevini tamamla`}
        onClick={onToggle}
        className={`grid h-[18px] w-[18px] shrink-0 place-items-center rounded-full border transition-colors ${
          done ? "border-success bg-success text-white" : "border-stone text-transparent hover:border-success hover:text-success"
        }`}
      >
        <Icon name="check" className="h-3 w-3" strokeWidth={2.6} />
      </button>
      <span className={`min-w-0 flex-1 truncate text-[14px] ${done ? "text-slate line-through decoration-slate/40" : "font-medium"}`}>{task.title}</span>
      {task.status === "in_progress" ? <span className="hidden rounded-full bg-violet/10 px-2 py-0.5 text-[11px] font-semibold text-violet sm:inline">{statusLabels.in_progress}</span> : null}
      {due ? <span className={`shrink-0 text-[12px] ${due.tone === "late" ? "font-semibold text-error-text" : "text-slate"}`}>{due.text}</span> : null}
      {task.assignee_name ? (
        <span title={task.assignee_name} aria-label={`Sorumlu: ${task.assignee_name}`} className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-graphite text-[10px] font-semibold text-onink">
          {initialsOf(task.assignee_name)}
        </span>
      ) : null}
    </li>
  );
}
