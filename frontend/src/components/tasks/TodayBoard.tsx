import { useEffect, useState } from "react";
import { ApiRequestError } from "../../lib/http.ts";
import { dueText, fetchToday, formatDay, moveTask, priorityLabels, type Task, type TaskStatus, type TodayView } from "../../lib/tasks.ts";
import { Alert, Spinner } from "../forms/Controls.tsx";
import { Icon } from "../ui/Icon.tsx";

type Section = { key: keyof Omit<TodayView, "today" | "load">; title: string; hint: string; tone: string };

const primary: Section[] = [
  { key: "overdue", title: "Gecikenler", hint: "Teslim tarihi geçmiş işleriniz", tone: "bg-error" },
  { key: "due_today", title: "Bugün", hint: "Bugün teslim edilecekler", tone: "bg-warning" },
  { key: "in_progress", title: "Sürenler", hint: "Üzerinde çalıştıklarınız", tone: "bg-violet" },
];
const secondary: Section[] = [
  { key: "unblocked", title: "Sırası gelenler", hint: "Bağlı oldukları görev son 7 günde tamamlandı", tone: "bg-success" },
  { key: "upcoming", title: "Bu hafta", hint: "Önümüzdeki 7 gün", tone: "bg-ink-soft" },
  { key: "waiting", title: "Bekleyenler", hint: "Önce başka görevlerin bitmesi gerekiyor", tone: "bg-mist" },
];

export function TodayBoard({ version, onOpen, onChanged }: { version: number; onOpen: (task: Task) => void; onChanged: (message: string) => void }) {
  const [view, setView] = useState<TodayView | null>(null);
  const [error, setError] = useState("");
  const [local, setLocal] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchToday()
      .then((next) => {
        if (!cancelled) setView(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiRequestError ? caught.message : "Günlük görünüm yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [version, local]);

  async function move(task: Task, status: TaskStatus) {
    setError("");
    try {
      await moveTask(task.id, status);
      onChanged(status === "done" ? `“${task.title}” tamamlandı.` : `“${task.title}” başlatıldı.`);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Görev güncellenemedi.");
    }
    setLocal((value) => value + 1);
  }

  if (error && !view) return <Alert tone="error">{error}</Alert>;
  if (!view) {
    return (
      <p role="status" className="flex items-center gap-2.5 py-12 text-[14px] text-slate">
        <Spinner /> Gününüz hazırlanıyor.
      </p>
    );
  }

  const attention = view.overdue.length + view.due_today.length;
  const total = primary.concat(secondary).reduce((sum, section) => sum + view[section.key].length, 0);

  return (
    <div className="space-y-6">
      {error ? <Alert tone="error">{error}</Alert> : null}
      <p className="text-[14px] text-ink-soft">
        <span className="font-medium text-midnight">{formatDay(view.today)}</span>
        {total === 0
          ? " · Size atanmış açık görev yok."
          : attention > 0
            ? ` · ${attention} iş bugün ilgilenmenizi bekliyor.`
            : " · Bugün için gecikmiş veya teslimi gelen işiniz yok."}
      </p>

      <div className="grid gap-x-8 gap-y-6 lg:grid-cols-3">
        {primary.map((section) => (
          <List key={section.key} section={section} tasks={view[section.key]} today={view.today} onOpen={onOpen} onMove={move} />
        ))}
      </div>
      <div className="grid gap-x-8 gap-y-6 border-t border-hairline pt-6 lg:grid-cols-3">
        {secondary.map((section) => (
          <List key={section.key} section={section} tasks={view[section.key]} today={view.today} onOpen={onOpen} onMove={move} quiet />
        ))}
      </div>

      {view.load.length > 1 ? (
        <section aria-labelledby="load-title" className="border-t border-hairline pt-6">
          <h2 id="load-title" className="text-[12px] font-medium uppercase tracking-[0.08em] text-slate">
            Ekibin iş yükü
          </h2>
          <table className="mt-2 w-full max-w-xl text-[13px]">
            <thead className="text-left text-[11.5px] text-slate">
              <tr>
                <th className="py-1.5 font-medium">Kişi</th>
                <th className="py-1.5 text-right font-medium">Açık</th>
                <th className="py-1.5 text-right font-medium">Bu hafta</th>
                <th className="py-1.5 text-right font-medium">Geciken</th>
                <th className="w-40 py-1.5 pl-4 font-medium">
                  <span className="sr-only">Dağılım</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {view.load.map((row) => {
                const widest = Math.max(...view.load.map((item) => item.open), 1);
                return (
                  <tr key={row.assignee_id ?? "none"}>
                    <td className="py-2">{row.name}</td>
                    <td className="py-2 text-right tabular-nums">{row.open}</td>
                    <td className="py-2 text-right tabular-nums text-slate">{row.this_week}</td>
                    <td className={`py-2 text-right tabular-nums ${row.overdue > 0 ? "font-medium text-error-text" : "text-slate"}`}>{row.overdue}</td>
                    <td className="py-2 pl-4">
                      <div aria-hidden className="flex h-1.5 overflow-hidden rounded-full bg-hairline">
                        <span className="bg-error" style={{ width: `${(row.overdue / widest) * 100}%` }} />
                        <span className="bg-ink-soft" style={{ width: `${((row.open - row.overdue) / widest) * 100}%` }} />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      ) : null}
    </div>
  );
}

function List({
  section,
  tasks,
  today,
  onOpen,
  onMove,
  quiet = false,
}: {
  section: Section;
  tasks: Task[];
  today: string;
  onOpen: (task: Task) => void;
  onMove: (task: Task, status: TaskStatus) => void;
  quiet?: boolean;
}) {
  return (
    <section aria-labelledby={`today-${section.key}`} className="min-w-0">
      <header className="flex items-baseline justify-between gap-3">
        <h2 id={`today-${section.key}`} className="flex items-center gap-2 text-[13px] font-semibold text-midnight">
          <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${section.tone}`} />
          {section.title}
        </h2>
        <span className="text-[12px] tabular-nums text-slate">{tasks.length}</span>
      </header>
      <p className="mt-0.5 text-[11.5px] text-slate">{section.hint}</p>
      {tasks.length === 0 ? (
        <p className="mt-3 text-[13px] text-slate/80">—</p>
      ) : (
        <ul className="mt-2 divide-y divide-hairline">
          {tasks.map((task) => {
            const due = dueText(task, today);
            return (
              <li key={task.id} className="group flex items-start gap-2.5 py-2.5">
                {!task.blocked ? (
                  <button
                    type="button"
                    role="checkbox"
                    aria-checked={false}
                    aria-label={`“${task.title}” görevini tamamla`}
                    onClick={() => onMove(task, "done")}
                    className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border border-stone text-transparent transition-colors hover:border-success hover:text-success"
                  >
                    <Icon name="check" className="h-2.5 w-2.5" strokeWidth={2.8} />
                  </button>
                ) : (
                  <Icon name="lock" className="mt-0.5 h-4 w-4 shrink-0 text-slate/70" />
                )}
                <button type="button" onClick={() => onOpen(task)} className="min-w-0 flex-1 text-left">
                  <span className={`block text-[13.5px] leading-5 ${quiet ? "text-ink-soft" : "font-medium text-midnight"} group-hover:underline`}>{task.title}</span>
                  <span className="mt-0.5 flex flex-wrap gap-x-2 text-[11.5px] text-slate">
                    {task.automatic ? <span className="font-medium text-violet">Otomatik</span> : null}
                    {due ? <span className={due.tone === "late" ? "text-error-text" : ""}>{due.text}</span> : null}
                    {task.priority === "urgent" || task.priority === "high" ? <span className="text-warning-text">{priorityLabels[task.priority]}</span> : null}
                    {task.customer_name ? <span>{task.customer_name}</span> : null}
                    {task.order_code ? <span>{task.order_code}</span> : null}
                    {task.project_name ? <span>{task.project_name}</span> : null}
                    {task.blocked ? <span>Bekliyor: {task.depends_on.filter((dep) => dep.status !== "done").map((dep) => dep.title).join(", ")}</span> : null}
                  </span>
                </button>
                {task.status === "todo" && !task.blocked && section.key !== "waiting" ? (
                  <button
                    type="button"
                    onClick={() => onMove(task, "in_progress")}
                    className="h-6 shrink-0 rounded px-1.5 text-[11.5px] font-medium text-slate opacity-0 transition-opacity hover:bg-midnight/[0.05] hover:text-graphite focus:opacity-100 group-hover:opacity-100"
                  >
                    Başla
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
