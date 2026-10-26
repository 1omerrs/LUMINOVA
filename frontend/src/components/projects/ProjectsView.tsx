import { useEffect, useState } from "react";
import { ApiRequestError } from "../../lib/http.ts";
import { useCreateIntent, type IntentCustomer, type IntentSource } from "../../lib/intent.ts";
import { readOnly, type WorkspaceModule } from "../../lib/modules.ts";
import {
  deleteProject,
  fetchProjects,
  fetchProjectSummary,
  projectSortLabels,
  projectStatuses,
  projectStatusLabels,
  projectStatusTone,
  type Project,
  type ProjectPage,
  type ProjectSort,
  type ProjectStatus,
  type ProjectSummary,
  type ProjectTemplate,
} from "../../lib/projects.ts";
import { dueText } from "../../lib/tasks.ts";
import { useWorkspace } from "../../lib/workspace.ts";
import { Alert, Button, Spinner } from "../forms/Controls.tsx";
import { ConfirmDialog } from "../ui/ConfirmDialog.tsx";
import { Icon } from "../ui/Icon.tsx";
import { Pagination } from "../ui/Pagination.tsx";
import { ModuleIcon } from "../workspace/ModuleIcon.tsx";
import { ProjectEditor } from "./ProjectEditor.tsx";
import { ProjectSheet } from "./ProjectSheet.tsx";
import { ProjectTemplatesSheet } from "./ProjectTemplatesSheet.tsx";

const PAGE_SIZE = 24;
type Load = { status: "loading" } | { status: "ready"; data: ProjectPage } | { status: "failed"; message: string };

export function ProjectsView({ module }: { module: WorkspaceModule }) {
  const { user, modules } = useWorkspace();
  const customersOn = modules.some((item) => item.key === "customers" && item.enabled);
  const salesOn = modules.some((item) => item.key === "sales" && item.enabled);
  const [templatesOpen, setTemplatesOpen] = useState(false);
  const [input, setInput] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<ProjectStatus | null>(null);
  const [sort, setSort] = useState<ProjectSort>("due_date");
  const [page, setPage] = useState(1);
  const [reload, setReload] = useState(0);
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [summary, setSummary] = useState<ProjectSummary | null>(null);
  const intent = useCreateIntent();
  const [editing, setEditing] = useState<{ project: Project | null; customer?: IntentCustomer | null; source?: IntentSource | null; template?: ProjectTemplate } | null>(() =>
    intent ? { project: null, customer: intent.customer, source: intent.source } : null,
  );
  const [viewing, setViewing] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Project | null>(null);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const next = input.trim();
    if (next === search) return;
    const timer = window.setTimeout(() => {
      setSearch(next);
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [input, search]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchProjects({ q: search, status, sort, page, pageSize: PAGE_SIZE }), fetchProjectSummary()])
      .then(([data, totals]) => {
        if (cancelled) return;
        if (data.items.length === 0 && data.page > 1) {
          setPage(data.page - 1);
          return;
        }
        setLoad({ status: "ready", data });
        setSummary(totals);
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoad({ status: "failed", message: error instanceof ApiRequestError ? error.message : "Projeler yüklenemedi." });
      });
    return () => {
      cancelled = true;
    };
  }, [search, status, sort, page, reload]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 4000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const data = load.status === "ready" ? load.data : null;
  const totalProjects = summary ? summary.planned + summary.active + summary.on_hold + summary.completed : null;
  const emptyWorkspace = totalProjects === 0;

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-4">
          <div className="min-w-0">
            <h1 className="font-display text-[22px] font-semibold tracking-[-0.02em] text-midnight sm:text-[24px]">{module.name}</h1>
            <p className="mt-0.5 text-[14px] text-slate">
              {summary && totalProjects ? (
                <>
                  {summary.active} devam eden · {summary.planned} planlanan · {summary.completed} tamamlanan
                  {summary.overdue > 0 ? (
                    <>
                      {" · "}
                      <span className="font-medium text-error-text">{summary.overdue} gecikmiş</span>
                    </>
                  ) : null}
                </>
              ) : (
                module.summary
              )}
            </p>
          </div>
        </div>
        <div className={`flex items-center gap-2 ${readOnly(module) ? "hidden" : ""}`}>
          <Button size="lg" variant="quiet" onClick={() => setTemplatesOpen(true)}>
            <Icon name="layers" className="h-4 w-4" />
            Şablonlar
          </Button>
          {emptyWorkspace ? null : (
            <Button size="lg" onClick={() => setEditing({ project: null })}>
              <Icon name="plus" className="h-4 w-4" strokeWidth={2} />
              Yeni proje
            </Button>
          )}
        </div>
      </section>

      {notice ? <Alert tone="success">{notice}</Alert> : null}

      {emptyWorkspace ? (
        <section className="rounded-2xl border border-mist/80 bg-surface px-6 py-16 text-center">
          <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-paper text-ink-soft ring-1 ring-inset ring-mist">
            <ModuleIcon name="projects" className="h-6 w-6" />
          </span>
          <h2 className="mt-5 text-[16px] font-semibold">İlk projenizi oluşturun.</h2>
          <p className="mx-auto mt-2 max-w-md text-[14px] leading-6 text-slate">
            Projeye görev bağladıkça ilerleme kendiliğinden hesaplanır. Bir müşteriye bağlayabilir, başlangıç ve teslim tarihi verebilirsiniz.
          </p>
          <Button className="mt-6" onClick={() => setEditing({ project: null })}>
            <Icon name="plus" className="h-4 w-4" strokeWidth={2} />
            Yeni proje
          </Button>
        </section>
      ) : (
        <>
          <section className="flex flex-col gap-3 rounded-2xl border border-mist/80 bg-surface px-4 py-3 sm:px-5 xl:flex-row xl:items-center xl:justify-between">
            <div role="tablist" aria-label="Proje durumu" className="flex flex-wrap gap-1 rounded-xl bg-cloud p-1">
              {([null, ...projectStatuses] as (ProjectStatus | null)[]).map((value) => {
                const count = value && summary ? summary[value] : null;
                return (
                  <button
                    key={value ?? "all"}
                    type="button"
                    role="tab"
                    aria-selected={status === value}
                    onClick={() => {
                      setStatus(value);
                      setPage(1);
                    }}
                    className={`h-8 shrink-0 rounded-[9px] px-3 text-[13px] font-semibold transition-colors ${
                      status === value ? "bg-surface text-graphite shadow-[0_1px_3px_rgba(16,19,28,0.12)]" : "text-slate hover:text-graphite"
                    }`}
                  >
                    {value ? projectStatusLabels[value] : "Tümü"}
                    {count ? <span className="ml-1 text-slate">{count}</span> : null}
                  </button>
                );
              })}
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <label className="relative block w-full sm:w-64">
                <span className="sr-only">Proje ara</span>
                <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate" />
                <input
                  type="search"
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  placeholder="Proje veya müşteri adı"
                  className="h-10 w-full rounded-lg border border-mist bg-surface pl-9 pr-3 text-[14px] outline-none placeholder:text-slate/70 hover:border-stone focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)]"
                />
              </label>
              <label className="flex items-center gap-2 text-[13px] text-slate">
                Sırala
                <select
                  aria-label="Sırala"
                  value={sort}
                  onChange={(event) => {
                    setSort(event.target.value as ProjectSort);
                    setPage(1);
                  }}
                  className="h-10 rounded-lg border border-mist bg-surface px-3 text-[14px] text-graphite outline-none hover:border-stone focus:border-violet"
                >
                  {(Object.keys(projectSortLabels) as ProjectSort[]).map((key) => (
                    <option key={key} value={key}>
                      {projectSortLabels[key]}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </section>

          {load.status === "failed" ? (
            <Alert tone="error">
              {load.message}{" "}
              <button type="button" onClick={() => setReload((value) => value + 1)} className="font-semibold underline">
                Tekrar dene
              </button>
            </Alert>
          ) : !data ? (
            <p role="status" className="flex items-center gap-2.5 py-12 text-[14px] text-slate">
              <Spinner className="h-4 w-4 text-violet" /> Projeler yükleniyor.
            </p>
          ) : data.items.length === 0 ? (
            <div className="rounded-2xl border border-mist/80 bg-surface px-5 py-14 text-center">
              <p className="text-[15px] font-semibold">{search ? `“${search}” ile eşleşen proje yok.` : "Bu durumda proje yok."}</p>
              {search ? (
                <button type="button" onClick={() => setInput("")} className="mt-4 text-[14px] font-semibold text-violet hover:underline">
                  Aramayı temizle
                </button>
              ) : null}
            </div>
          ) : (
            <>
              <ul className="grid grid-cols-1 gap-4 md:grid-cols-2 2xl:grid-cols-3">
                {data.items.map((project) => (
                  <li key={project.id} className="min-w-0">
                    <ProjectCard project={project} today={data.today} onOpen={() => setViewing(project.id)} />
                  </li>
                ))}
              </ul>
              {data.total > data.page_size ? (
                <div className="overflow-hidden rounded-2xl border border-mist/80 bg-surface">
                  <Pagination page={data.page} pageSize={data.page_size} total={data.total} noun="proje" onPage={setPage} />
                </div>
              ) : null}
            </>
          )}
        </>
      )}

      {editing ? (
        <ProjectEditor
          key={editing.project?.id ?? "new"}
          project={editing.project}
          customersOn={customersOn}
          salesOn={salesOn}
          initialCustomer={editing.customer ?? null}
          initialTemplate={editing.template ?? null}
          initialSource={editing.source ? { [editing.source.kind]: { id: editing.source.id, label: editing.source.label } } : {}}
          onClose={() => setEditing(null)}
          onSaved={(project, created) => {
            setEditing(null);
            setNotice(created ? `“${project.name}” oluşturuldu.` : `“${project.name}” güncellendi.`);
            setReload((value) => value + 1);
            setViewing(project.id);
          }}
        />
      ) : null}

      {viewing && !editing && !deleting ? (
        <ProjectSheet
          key={viewing}
          projectId={viewing}
          assigneeId={user.id}
          onClose={() => setViewing(null)}
          onEdit={(project) => setEditing({ project })}
          onDelete={(project) => setDeleting(project)}
          onChanged={() => setReload((value) => value + 1)}
        />
      ) : null}

      {templatesOpen ? (
        <ProjectTemplatesSheet
          onClose={() => setTemplatesOpen(false)}
          onUse={(template) => {
            setTemplatesOpen(false);
            setEditing({ project: null, template });
          }}
        />
      ) : null}

      {deleting ? (
        <ConfirmDialog
          title="Proje silinsin mi?"
          confirmLabel="Projeyi sil"
          pendingLabel="Siliniyor"
          onClose={() => setDeleting(null)}
          onConfirm={async () => {
            await deleteProject(deleting.id);
            setNotice(`“${deleting.name}” silindi.`);
            setDeleting(null);
            setViewing(null);
            setReload((value) => value + 1);
          }}
        >
          “{deleting.name}” listeden kaldırılır.{" "}
          {deleting.task_total > 0 ? `Bağlı ${deleting.task_total} görev silinmez; görev panosunda projesiz olarak kalır.` : "Bu projeye bağlı görev yok."}
        </ConfirmDialog>
      ) : null}
    </div>
  );
}

function ProjectCard({ project, today, onOpen }: { project: Project; today: string; onOpen: () => void }) {
  const due = dueText({ due_date: project.due_date, status: project.status === "completed" ? "done" : "todo" }, today);
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex h-full w-full flex-col rounded-2xl border border-mist/80 bg-surface p-5 text-left transition-[border-color,box-shadow] hover:border-stone hover:shadow-[0_10px_28px_-18px_rgba(32,36,50,0.45)]"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <span className="block truncate text-[15px] font-semibold">{project.name}</span>
          <span className="mt-0.5 block truncate text-[13px] text-slate">{project.customer_name ?? "Müşteri bağlı değil"}</span>
        </div>
        <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-[12px] font-semibold ${projectStatusTone[project.status]}`}>{projectStatusLabels[project.status]}</span>
      </div>
      <div className="mt-5">
        <div className="flex items-baseline justify-between text-[13px]">
          <span className="text-slate">{project.task_total === 0 ? "Görev yok" : `${project.task_done} / ${project.task_total} görev`}</span>
          <span className="font-semibold tabular-nums">%{project.progress}</span>
        </div>
        <div aria-hidden className="mt-2 h-1.5 overflow-hidden rounded-full bg-mist/60">
          <div className={`h-full rounded-full ${project.status === "completed" ? "bg-success" : "bg-violet"}`} style={{ width: `${project.progress}%` }} />
        </div>
        {project.milestone_total > 0 ? (
          <p className="mt-2 truncate text-[12px] text-slate">
            {project.milestone_done} / {project.milestone_total} aşama
            {project.next_milestone ? ` · Sıradaki: ${project.next_milestone}` : " · tüm aşamalar tamam"}
          </p>
        ) : null}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2 text-[12px]">
        {due ? (
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-semibold ${
              project.overdue ? "bg-error/[0.08] text-error-text" : due.tone === "soon" ? "bg-violet/10 text-violet" : "text-slate"
            }`}
          >
            <Icon name="calendar" className="h-3 w-3" />
            {due.text}
          </span>
        ) : (
          <span className="text-slate">Teslim tarihi yok</span>
        )}
        {project.task_overdue > 0 ? <span className="font-semibold text-error-text">{project.task_overdue} görev gecikmiş</span> : null}
        {project.quote_code || project.order_code ? (
          <span className="ml-auto font-mono text-[11.5px] text-slate">{[project.quote_code, project.order_code].filter(Boolean).join(" · ")}</span>
        ) : null}
      </div>
    </button>
  );
}
