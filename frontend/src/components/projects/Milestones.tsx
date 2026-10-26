import { useEffect, useState, type FormEvent } from "react";
import { ApiRequestError } from "../../lib/http.ts";
import { addMilestone, deleteMilestone, fetchMilestones, moveMilestone, updateMilestone, type Milestone } from "../../lib/projects.ts";
import { formatDay } from "../../lib/tasks.ts";
import { Alert, Button, Spinner } from "../forms/Controls.tsx";
import { Icon } from "../ui/Icon.tsx";

const input =
  "h-10 rounded-lg border border-mist bg-surface px-3 text-[14px] text-graphite outline-none hover:border-stone focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)]";
const iconButton = "grid h-8 w-8 place-items-center rounded-lg text-slate transition-colors hover:bg-cloud hover:text-graphite disabled:opacity-30 disabled:hover:bg-transparent";

export function Milestones({ projectId, onChanged }: { projectId: string; onChanged: () => void }) {
  const [rows, setRows] = useState<Milestone[] | null>(null);
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchMilestones(projectId)
      .then((next) => {
        if (!cancelled) setRows(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiRequestError ? caught.message : "Aşamalar yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  async function run(key: string, action: () => Promise<Milestone[]>) {
    setBusy(key);
    setError("");
    try {
      setRows(await action());
      onChanged();
      return true;
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Aşama kaydedilemedi.");
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function onAdd(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const clean = title.trim();
    if (clean.length < 2) {
      setError("Aşama adı en az 2 karakter olmalı.");
      return;
    }
    if (await run("add", () => addMilestone(projectId, { title: clean, due_date: due || null, done: false }))) {
      setTitle("");
      setDue("");
    }
  }

  const done = rows?.filter((row) => row.done).length ?? 0;

  return (
    <section aria-labelledby="milestones-title">
      <div className="flex items-center justify-between gap-3">
        <h3 id="milestones-title" className="text-[14px] font-semibold">
          Aşamalar
        </h3>
        {rows && rows.length > 0 ? (
          <span className="text-[13px] text-slate">
            {done} / {rows.length} tamamlandı
          </span>
        ) : null}
      </div>

      {error ? (
        <div className="mt-3">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}

      {rows === null && !error ? (
        <p className="mt-3 flex items-center gap-2 text-[13px] text-slate">
          <Spinner /> Aşamalar yükleniyor
        </p>
      ) : null}

      {rows && rows.length === 0 ? (
        <p className="mt-3 rounded-xl border border-dashed border-mist px-4 py-5 text-center text-[13px] text-slate">
          Projeyi keşif, onay, teslim gibi aşamalara bölün; sıradaki aşama proje kartında görünür.
        </p>
      ) : null}

      {rows && rows.length > 0 ? (
        <ol className="mt-3 divide-y divide-mist/60 overflow-hidden rounded-xl border border-mist/80">
          {rows.map((row, index) => (
            <li key={row.id} className="flex items-center gap-3 bg-surface px-4 py-2.5">
              <button
                type="button"
                role="checkbox"
                aria-checked={row.done}
                aria-label={row.done ? `“${row.title}” aşamasını yeniden aç` : `“${row.title}” aşamasını tamamla`}
                disabled={busy !== null}
                onClick={() => void run(row.id, () => updateMilestone(projectId, row.id, { title: row.title, due_date: row.due_date, done: !row.done }))}
                className={`grid h-[18px] w-[18px] shrink-0 place-items-center rounded-[5px] border transition-colors ${
                  row.done ? "border-success bg-success text-white" : "border-stone text-transparent hover:border-success hover:text-success"
                }`}
              >
                <Icon name="check" className="h-3 w-3" strokeWidth={2.6} />
              </button>
              <span className="w-5 shrink-0 text-right text-[12px] tabular-nums text-slate">{index + 1}.</span>
              <span className={`min-w-0 flex-1 truncate text-[14px] ${row.done ? "text-slate line-through decoration-slate/40" : "font-medium"}`}>{row.title}</span>
              {row.due_date ? (
                <span className={`shrink-0 text-[12px] ${row.overdue ? "font-semibold text-error-text" : "text-slate"}`}>
                  {formatDay(row.due_date)}
                  {row.overdue ? " · gecikti" : ""}
                </span>
              ) : null}
              <span className="flex shrink-0 items-center">
                <button
                  type="button"
                  aria-label={`“${row.title}” aşamasını yukarı taşı`}
                  disabled={index === 0 || busy !== null}
                  onClick={() => void run(row.id, () => moveMilestone(projectId, row.id, "up"))}
                  className={iconButton}
                >
                  <Icon name="chevron-down" className="h-4 w-4 rotate-180" />
                </button>
                <button
                  type="button"
                  aria-label={`“${row.title}” aşamasını aşağı taşı`}
                  disabled={index === rows.length - 1 || busy !== null}
                  onClick={() => void run(row.id, () => moveMilestone(projectId, row.id, "down"))}
                  className={iconButton}
                >
                  <Icon name="chevron-down" className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  aria-label={`“${row.title}” aşamasını kaldır`}
                  disabled={busy !== null}
                  onClick={() => void run(row.id, () => deleteMilestone(projectId, row.id))}
                  className={`${iconButton} hover:text-error-text`}
                >
                  <Icon name="trash" className="h-4 w-4" />
                </button>
              </span>
            </li>
          ))}
        </ol>
      ) : null}

      <form noValidate onSubmit={(event) => void onAdd(event)} className="mt-3 flex flex-wrap gap-2">
        <label className="min-w-0 flex-1 basis-56">
          <span className="sr-only">Yeni aşama adı</span>
          <input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={160} placeholder="Yeni aşama, ör. Tasarım onayı" className={`${input} w-full`} />
        </label>
        <label>
          <span className="sr-only">Aşama hedef tarihi</span>
          <input type="date" value={due} onChange={(event) => setDue(event.target.value)} className={input} />
        </label>
        <Button type="submit" variant="quiet" pending={busy === "add"} pendingLabel="Ekleniyor">
          <Icon name="plus" className="h-4 w-4" /> Ekle
        </Button>
      </form>
    </section>
  );
}
