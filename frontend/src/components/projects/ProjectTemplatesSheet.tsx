import { useEffect, useId, useState } from "react";
import { ApiRequestError } from "../../lib/http.ts";
import { deleteProjectTemplate, fetchProjectTemplates, saveProjectTemplate, type ProjectTemplate, type TemplateTask } from "../../lib/projects.ts";
import { Alert, Button, Field, Spinner } from "../forms/Controls.tsx";
import { Icon } from "../ui/Icon.tsx";
import { Sheet } from "../ui/Sheet.tsx";

const control =
  "h-9 w-full rounded-lg border border-mist bg-surface px-2.5 text-[13px] text-graphite outline-none hover:border-stone focus:border-violet";

const blankTask = (stage = ""): TemplateTask => ({ stage, title: "", description: null, priority: "normal", duration_days: 1, depends_on: [] });

export function ProjectTemplatesSheet({ onClose, onUse }: { onClose: () => void; onUse: (template: ProjectTemplate) => void }) {
  const [templates, setTemplates] = useState<ProjectTemplate[] | null>(null);
  const [editing, setEditing] = useState<{ template: ProjectTemplate | null } | null>(null);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchProjectTemplates()
      .then((next) => {
        if (!cancelled) setTemplates(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiRequestError ? caught.message : "Şablonlar yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [version]);

  if (editing) {
    return (
      <EditTemplate
        template={editing.template}
        onBack={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          setVersion((value) => value + 1);
        }}
      />
    );
  }

  return (
    <Sheet
      title="Proje şablonları"
      description="Aşamaları, görevleri, süreleri ve sıralarını bir kez tanımlayın. Yeni projede şablonu seçtiğinizde görevler ve tarihler kendiliğinden oluşur."
      onClose={onClose}
      footer={
        <Button onClick={() => setEditing({ template: null })}>
          <Icon name="plus" className="h-4 w-4" /> Yeni şablon
        </Button>
      }
    >
      {error ? <Alert tone="error">{error}</Alert> : null}
      {templates === null && !error ? (
        <p className="flex items-center gap-2 text-[14px] text-slate">
          <Spinner /> Yükleniyor
        </p>
      ) : null}
      {templates && templates.length === 0 ? (
        <p className="text-[14px] leading-6 text-slate">
          Henüz şablon yok. Örneğin “Mutfak montajı”: Keşif (ölçü al, onay), Üretim (kesim, boya), Teslim (montaj). Her görevin süresini ve hangi görevden sonra başlayacağını yazın; başlangıç tarihi verildiğinde takvim hesaplanır.
        </p>
      ) : null}
      {templates && templates.length > 0 ? (
        <ul className="divide-y divide-hairline">
          {templates.map((template) => (
            <li key={template.id} className="py-3.5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[14px] font-semibold">{template.name}</p>
                  <p className="mt-0.5 text-[12.5px] text-slate">
                    {template.stages.length} aşama · {template.items.length} görev · yaklaşık {template.total_days} gün
                  </p>
                  <p className="mt-1 truncate text-[12px] text-slate">{template.stages.join(" → ")}</p>
                </div>
                <div className="flex shrink-0 gap-1.5">
                  <Button size="sm" variant="quiet" onClick={() => setEditing({ template })}>
                    Düzenle
                  </Button>
                  <Button size="sm" onClick={() => onUse(template)}>
                    Proje başlat
                  </Button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </Sheet>
  );
}

function EditTemplate({ template, onBack, onSaved }: { template: ProjectTemplate | null; onBack: () => void; onSaved: () => void }) {
  const stagesId = useId();
  const [name, setName] = useState(template?.name ?? "");
  const [tasks, setTasks] = useState<TemplateTask[]>(template?.items.length ? template.items : [blankTask(), blankTask()]);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<"save" | "delete" | null>(null);
  const stages = [...new Set(tasks.map((task) => task.stage.trim()).filter(Boolean))];

  function update(index: number, patch: Partial<TemplateTask>) {
    setTasks((current) => current.map((task, position) => (position === index ? { ...task, ...patch } : task)));
  }

  function remove(index: number) {
    setTasks((current) =>
      current
        .filter((_, position) => position !== index)
        .map((task) => ({ ...task, depends_on: task.depends_on.filter((parent) => parent !== index).map((parent) => (parent > index ? parent - 1 : parent)) })),
    );
  }

  async function save() {
    if (name.trim().length < 2) return setError("Şablona en az 2 karakterlik bir ad verin.");
    if (tasks.some((task) => task.title.trim().length < 2)) return setError("Her görevin en az 2 karakterlik bir adı olmalı.");
    if (tasks.some((task) => task.stage.trim().length < 2)) return setError("Her görev için bir aşama adı yazın (ör. Keşif, Üretim, Teslim).");
    setPending("save");
    setError("");
    try {
      await saveProjectTemplate({ name: name.trim(), description: null, items: tasks.map((task) => ({ ...task, title: task.title.trim(), stage: task.stage.trim() })) }, template?.id);
      onSaved();
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Şablon kaydedilemedi.");
      setPending(null);
    }
  }

  async function removeTemplate() {
    if (!template) return;
    setPending("delete");
    try {
      await deleteProjectTemplate(template.id);
      onSaved();
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Şablon silinemedi.");
      setPending(null);
    }
  }

  return (
    <Sheet
      wide
      title={template ? "Proje şablonunu düzenle" : "Yeni proje şablonu"}
      description="Süre takvim günüdür. Bir görev, seçtiğiniz önceki görevler bittikten sonraki gün başlar; seçim yoksa proje başlangıcında."
      busy={pending !== null}
      onClose={onBack}
      footer={
        <>
          {template ? (
            <Button variant="ghost" className="mr-auto text-error-text" onClick={() => void removeTemplate()} pending={pending === "delete"} pendingLabel="Siliniyor">
              Şablonu sil
            </Button>
          ) : null}
          <Button variant="quiet" onClick={onBack} disabled={pending !== null}>
            Geri
          </Button>
          <Button onClick={() => void save()} pending={pending === "save"} pendingLabel="Kaydediliyor">
            Şablonu kaydet
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Field label="Şablon adı" value={name} onValue={setName} maxLength={120} placeholder="Ör. Mutfak montajı" />
        <datalist id={stagesId}>
          {stages.map((stage) => (
            <option key={stage} value={stage} />
          ))}
        </datalist>
        <ol className="space-y-3">
          {tasks.map((task, index) => (
            <li key={index} className="grid grid-cols-[24px_minmax(0,1fr)] gap-x-2 gap-y-2 border-b border-hairline pb-3 sm:grid-cols-[24px_140px_minmax(0,1fr)_92px_32px]">
              <span className="pt-2 text-right text-[12px] tabular-nums text-slate">{index + 1}.</span>
              <input
                aria-label={`${index + 1}. görevin aşaması`}
                list={stagesId}
                value={task.stage}
                onChange={(event) => update(index, { stage: event.target.value })}
                maxLength={160}
                placeholder="Aşama"
                className={control}
              />
              <input
                aria-label={`${index + 1}. görev`}
                value={task.title}
                onChange={(event) => update(index, { title: event.target.value })}
                maxLength={200}
                placeholder="Görev"
                className={`${control} col-start-2 sm:col-start-auto`}
              />
              <label className="col-start-2 flex items-center gap-1.5 sm:col-start-auto">
                <input
                  aria-label={`${index + 1}. görevin süresi (gün)`}
                  type="number"
                  min={1}
                  max={365}
                  value={task.duration_days}
                  onChange={(event) => update(index, { duration_days: Math.max(1, Math.min(365, Number(event.target.value) || 1)) })}
                  className={control}
                />
                <span className="text-[12px] text-slate">gün</span>
              </label>
              <button
                type="button"
                aria-label={`${index + 1}. görevi kaldır`}
                onClick={() => remove(index)}
                disabled={tasks.length === 1}
                className="col-start-2 grid h-9 w-8 place-items-center justify-self-end rounded-md text-slate hover:bg-midnight/[0.05] hover:text-error-text disabled:opacity-30 sm:col-start-auto"
              >
                <Icon name="trash" className="h-4 w-4" />
              </button>
              {index > 0 ? (
                <div className="col-start-2 flex flex-wrap items-center gap-1.5 sm:col-span-4">
                  <span className="text-[12px] text-slate">Önce bitmeli:</span>
                  {tasks.slice(0, index).map((parent, parentIndex) => {
                    const on = task.depends_on.includes(parentIndex);
                    return (
                      <button
                        key={parentIndex}
                        type="button"
                        aria-pressed={on}
                        onClick={() =>
                          update(index, { depends_on: on ? task.depends_on.filter((value) => value !== parentIndex) : [...task.depends_on, parentIndex].sort((a, b) => a - b) })
                        }
                        className={`h-6 max-w-[180px] truncate rounded px-2 text-[11.5px] ring-1 ring-inset transition-colors ${
                          on ? "bg-midnight text-onink ring-midnight" : "bg-surface text-slate ring-mist hover:text-graphite"
                        }`}
                      >
                        {parentIndex + 1}. {parent.title || "görev"}
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </li>
          ))}
        </ol>
        <Button
          variant="quiet"
          size="sm"
          onClick={() => setTasks((current) => [...current, { ...blankTask(current.at(-1)?.stage ?? ""), depends_on: current.length ? [current.length - 1] : [] }])}
          disabled={tasks.length >= 60}
        >
          <Icon name="plus" className="h-3.5 w-3.5" /> Görev ekle
        </Button>
      </div>
    </Sheet>
  );
}
