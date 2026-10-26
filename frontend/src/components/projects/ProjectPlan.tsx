import { useState } from "react";
import { Link } from "react-router";
import { ApiRequestError } from "../../lib/http.ts";
import { reschedule, type PlanRisk, type PlanTask, type Project, type ProjectPlan, type ScheduleChange } from "../../lib/projects.ts";
import { formatDay } from "../../lib/tasks.ts";
import { Alert, Button } from "../forms/Controls.tsx";

const dayMs = 86_400_000;
const short = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "short", timeZone: "UTC" });
const utc = (iso: string) => Date.parse(`${iso}T00:00:00Z`);
const shift = (iso: string, days: number) => new Date(utc(iso) + days * dayMs).toISOString().slice(0, 10);
const span = (from: string, to: string) => Math.round((utc(to) - utc(from)) / dayMs);

export function PlanProgress({ project, plan }: { project: Project; plan: ProjectPlan }) {
  const expected = plan.expected_progress;
  const gap = expected === null ? 0 : expected - plan.actual_progress;
  const late = plan.delay_days > 0;
  return (
    <section aria-labelledby="progress-title" className="border-b border-hairline pb-5">
      <h3 id="progress-title" className="text-[12px] font-semibold uppercase tracking-[0.08em] text-slate">
        İlerleme
      </h3>
      <div className="mt-3 grid grid-cols-2 gap-6 sm:grid-cols-3">
        <div>
          <p className="font-display text-[30px] font-semibold leading-none tracking-tight tabular-nums">%{plan.actual_progress}</p>
          <p className="mt-1.5 text-[12.5px] text-slate">Gerçekleşen · görev sürelerine göre</p>
        </div>
        <div>
          <p className={`font-display text-[30px] font-semibold leading-none tracking-tight tabular-nums ${gap >= 15 ? "text-warning-text" : "text-ink-soft"}`}>
            {expected === null ? "—" : `%${expected}`}
          </p>
          <p className="mt-1.5 text-[12.5px] text-slate">{expected === null ? "Hedef için tarih gerekli" : "Plana göre bugün olması gereken"}</p>
        </div>
        <div className="col-span-2 sm:col-span-1">
          <p className={`text-[15px] font-semibold tabular-nums ${late ? "text-error-text" : "text-graphite"}`}>
            {plan.projected_finish ? formatDay(plan.projected_finish) : "Hesaplanamıyor"}
          </p>
          <p className="mt-1.5 text-[12.5px] leading-5 text-slate">
            Tahmini bitiş
            {project.due_date ? ` · hedef ${formatDay(project.due_date)}` : ""}
            {late ? <span className="font-semibold text-error-text"> · {plan.delay_days} gün geç</span> : project.due_date && plan.projected_finish ? " · zamanında" : ""}
          </p>
        </div>
      </div>
      <div
        role="progressbar"
        aria-label="Gerçekleşen ilerleme"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={plan.actual_progress}
        className="relative mt-5 h-2 rounded-full bg-mist/70"
      >
        <div className="h-full rounded-full bg-violet transition-[width] duration-500 ease-out" style={{ width: `${plan.actual_progress}%` }} />
        {expected !== null ? (
          <span aria-hidden title={`Plana göre %${expected}`} className="absolute -top-1 h-4 w-0.5 rounded bg-midnight" style={{ left: `calc(${expected}% - 1px)` }} />
        ) : null}
      </div>
      <p className="mt-2 text-[12px] text-slate">
        {project.task_done} / {project.task_total} görev tamamlandı
        {expected !== null ? " · siyah çizgi plana göre bugünkü hedef" : ""}
      </p>
    </section>
  );
}

export function RescheduleStrip({ projectId, count, onApplied }: { projectId: string; count: number; onApplied: () => void }) {
  const [changes, setChanges] = useState<ScheduleChange[] | null>(null);
  const [pending, setPending] = useState<"preview" | "apply" | null>(null);
  const [error, setError] = useState("");

  async function run(apply: boolean) {
    setPending(apply ? "apply" : "preview");
    setError("");
    try {
      const result = await reschedule(projectId, apply);
      if (apply) {
        setChanges(null);
        onApplied();
      } else {
        setChanges(result.changes);
      }
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Takvim hesaplanamadı.");
    }
    setPending(null);
  }

  return (
    <section className="rounded-xl bg-violet-wash/70 px-4 py-3.5 ring-1 ring-inset ring-lavender">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-[13.5px] leading-5 text-graphite">
          <span className="font-semibold">{count} görevin tarihi</span> bağımlılıklarına ve proje takvimine göre güncel değil. Önceki işler erken biterse sonrakiler öne alınır, gecikirse ileri kayar.
        </p>
        {changes === null ? (
          <Button size="sm" variant="dark" onClick={() => void run(false)} pending={pending === "preview"} pendingLabel="Hesaplanıyor">
            Değişiklikleri gör
          </Button>
        ) : null}
      </div>
      {error ? (
        <div className="mt-3">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}
      {changes ? (
        <div className="mt-3">
          <ul className="divide-y divide-lavender/70 text-[13px]">
            {changes.map((change) => (
              <li key={change.task_id} className="flex items-center justify-between gap-3 py-2">
                <span className="min-w-0 truncate font-medium">{change.title}</span>
                <span className="shrink-0 tabular-nums text-slate">
                  {change.old_due ? short.format(new Date(utc(change.old_due))) : "tarihsiz"} → <span className="font-semibold text-graphite">{short.format(new Date(utc(change.new_due)))}</span>
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-3 flex justify-end gap-2">
            <Button size="sm" variant="quiet" onClick={() => setChanges(null)} disabled={pending !== null}>
              Vazgeç
            </Button>
            <Button size="sm" onClick={() => void run(true)} pending={pending === "apply"} pendingLabel="Uygulanıyor">
              {changes.length} tarihi güncelle
            </Button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function barTone(task: PlanTask): string {
  if (task.status === "done") return "bg-sage/70";
  if (task.overdue) return "bg-error/75";
  if (task.blocked)
    return `bg-[repeating-linear-gradient(135deg,#d9d6ce_0_4px,#ebe9e3_4px_8px)] ring-1 ring-inset ${task.critical ? "ring-violet/70" : "ring-mist"}`;
  if (task.critical) return "bg-violet";
  return "bg-violet/40";
}

export function Timeline({ project, plan }: { project: Project; plan: ProjectPlan }) {
  const dated = plan.tasks.filter((task) => task.due_date);
  const undated = plan.tasks.filter((task) => !task.due_date);
  if (dated.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-mist px-4 py-8 text-center text-[13.5px] leading-6 text-slate">
        Zaman çizelgesi için görevlerde tarih olmalı. Görevlere teslim tarihi verin ya da süreleriyle birlikte gelen bir proje şablonu kullanın.
      </p>
    );
  }
  const points = [
    plan.today,
    ...dated.map((task) => task.start_date ?? task.due_date ?? plan.today),
    ...dated.map((task) => task.due_date ?? plan.today),
    ...(project.start_date ? [project.start_date] : []),
    ...(project.due_date ? [project.due_date] : []),
    ...(plan.projected_finish ? [plan.projected_finish] : []),
  ].sort();
  const from = shift(points[0], -1);
  const to = shift(points[points.length - 1], 2);
  const days = span(from, to);
  const at = (iso: string) => `${(span(from, iso) / days) * 100}%`;
  const step = days <= 16 ? 2 : days <= 45 ? 7 : days <= 120 ? 14 : 30;
  const ticks: string[] = [];
  for (let offset = 1; offset < days; offset += step) ticks.push(shift(from, offset));

  const groups = [
    ...plan.milestones.map((milestone) => ({ key: milestone.id, milestone, tasks: dated.filter((task) => task.milestone_id === milestone.id) })),
    { key: "other", milestone: null, tasks: dated.filter((task) => !task.milestone_id || !plan.milestones.some((item) => item.id === task.milestone_id)) },
  ].filter((group) => group.tasks.length > 0 || group.milestone?.due_date);

  const markers = (
    <>
      <span aria-hidden className="absolute inset-y-0 w-px bg-error/80" style={{ left: at(plan.today) }} />
      {project.due_date ? <span aria-hidden className="absolute inset-y-0 border-l border-dashed border-midnight/35" style={{ left: at(shift(project.due_date, 1)) }} /> : null}
    </>
  );

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <div className="min-w-[620px]">
          <div className="grid grid-cols-[190px_minmax(0,1fr)] border-b border-hairline pb-1.5">
            <span className="text-[11.5px] font-semibold uppercase tracking-[0.08em] text-slate">Görev</span>
            <div className="relative h-4">
              {ticks.map((tick) => (
                <span key={tick} className="absolute -translate-x-1/2 whitespace-nowrap text-[11px] tabular-nums text-slate" style={{ left: at(tick) }}>
                  {short.format(new Date(utc(tick)))}
                </span>
              ))}
            </div>
          </div>
          {groups.map((group) => (
            <div key={group.key} className="border-b border-hairline py-1.5">
              <div className="grid grid-cols-[190px_minmax(0,1fr)] items-center">
                <span className={`truncate text-[12.5px] font-semibold ${group.milestone?.done ? "text-slate line-through decoration-slate/40" : "text-graphite"}`}>
                  {group.milestone ? group.milestone.title : "Aşamasız görevler"}
                </span>
                <div className="relative h-6">
                  {markers}
                  {group.milestone?.due_date ? (
                    <span
                      aria-label={`${group.milestone.title} hedefi ${formatDay(group.milestone.due_date)}`}
                      title={`${group.milestone.title} · ${formatDay(group.milestone.due_date)}`}
                      className={`absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rotate-45 ${
                        group.milestone.done ? "bg-sage" : group.milestone.overdue ? "bg-error" : "bg-midnight"
                      }`}
                      style={{ left: at(shift(group.milestone.due_date, 1)) }}
                    />
                  ) : null}
                </div>
              </div>
              {group.tasks.map((task) => {
                const start = task.start_date ?? task.due_date ?? plan.today;
                const end = shift(task.due_date ?? start, 1);
                return (
                  <div key={task.id} className="grid grid-cols-[190px_minmax(0,1fr)] items-center">
                    <span className="flex min-w-0 items-center gap-1.5 pl-3 text-[12.5px]">
                      <span className={`truncate ${task.status === "done" ? "text-slate" : "text-ink-soft"}`}>{task.title}</span>
                      {task.assignee_name ? <span className="shrink-0 text-[11px] text-slate">· {task.assignee_name.split(" ")[0]}</span> : null}
                    </span>
                    <div className="relative h-7">
                      {markers}
                      <span
                        title={`${task.title}: ${formatDay(start)} – ${formatDay(task.due_date ?? start)}${task.critical ? " · kritik yol" : ""}${task.blocked ? " · önceki görevi bekliyor" : ""}`}
                        className={`absolute top-1.5 h-4 rounded-[4px] ${barTone(task)}`}
                        style={{ left: at(start), width: `max(6px, calc(${at(end)} - ${at(start)}))` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-[11.5px] text-slate">
        <Legend className="bg-violet">Kritik yol</Legend>
        <Legend className="bg-violet/40">Diğer</Legend>
        <Legend className="bg-[repeating-linear-gradient(135deg,#d9d6ce_0_3px,#ebe9e3_3px_6px)]">Önceki işi bekliyor</Legend>
        <Legend className="bg-error/75">Gecikmiş</Legend>
        <Legend className="bg-sage/70">Tamamlandı</Legend>
        <li className="flex items-center gap-1.5">
          <span aria-hidden className="h-3 w-px bg-error/60" /> Bugün
        </li>
        {project.due_date ? (
          <li className="flex items-center gap-1.5">
            <span aria-hidden className="h-3 border-l border-dashed border-midnight/50" /> Teslim hedefi
          </li>
        ) : null}
      </ul>
      {undated.length > 0 ? (
        <p className="text-[12.5px] text-slate">
          Tarihsiz {undated.length} görev çizelgede gösterilmiyor: {undated.slice(0, 3).map((task) => `“${task.title}”`).join(", ")}
          {undated.length > 3 ? "…" : ""}
        </p>
      ) : null}
    </div>
  );
}

function Legend({ className, children }: { className: string; children: string }) {
  return (
    <li className="flex items-center gap-1.5">
      <span aria-hidden className={`h-2.5 w-4 rounded-[3px] ${className}`} />
      {children}
    </li>
  );
}

const severityDot: Record<PlanRisk["severity"], string> = { high: "bg-error", medium: "bg-warning", low: "bg-slate/50" };
const severityLabel: Record<PlanRisk["severity"], string> = { high: "Yüksek", medium: "Orta", low: "Düşük" };

export function Risks({ plan, projectId }: { plan: ProjectPlan; projectId: string }) {
  if (plan.risks.length === 0) {
    return (
      <div className="rounded-xl border border-hairline px-4 py-6 text-[13.5px] leading-6 text-slate">
        <p className="font-semibold text-graphite">Şu an dikkat gerektiren bir şey yok.</p>
        Gecikme, darboğaz, sorumlusu olmayan yakın görev veya hedefi aşan plan oluştuğunda burada nedeniyle birlikte görünür.
      </div>
    );
  }
  return (
    <ul className="divide-y divide-hairline border-y border-hairline">
      {plan.risks.map((risk, index) => (
        <li key={`${risk.kind}-${risk.task_id ?? index}`} className="flex items-start gap-3 py-3.5">
          <span aria-label={`Önem: ${severityLabel[risk.severity]}`} className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${severityDot[risk.severity]}`} />
          <div className="min-w-0 flex-1">
            <p className="text-[14px] font-semibold">{risk.title}</p>
            <p className="mt-0.5 text-[13px] leading-5 text-slate">{risk.detail}</p>
          </div>
          {risk.task_id ? (
            <Link to={`/panel/gorevler?proje=${projectId}&gorev=${risk.task_id}`} className="shrink-0 text-[13px] font-semibold text-violet hover:underline">
              Görevi aç
            </Link>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
