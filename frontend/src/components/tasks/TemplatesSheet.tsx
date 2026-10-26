import { useCallback, useEffect, useState } from "react";
import { fetchCustomers } from "../../lib/customers.ts";
import { ApiRequestError } from "../../lib/http.ts";
import {
  applyTemplate,
  deleteTemplate,
  fetchTemplates,
  priorities,
  priorityLabels,
  saveTemplate,
  type Assignee,
  type TaskPriority,
  type TaskTemplate,
  type TemplateStep,
} from "../../lib/tasks.ts";
import { Alert, Button, Field, Spinner } from "../forms/Controls.tsx";
import { Picker, type PickerOption } from "../forms/Picker.tsx";
import { Icon } from "../ui/Icon.tsx";
import { Sheet } from "../ui/Sheet.tsx";

const control =
  "h-9 w-full rounded-lg border border-mist bg-surface px-2.5 text-[13px] text-graphite outline-none hover:border-stone focus:border-violet";
type Mode = { kind: "list" } | { kind: "edit"; template: TaskTemplate | null } | { kind: "apply"; template: TaskTemplate };

const blankStep = (): TemplateStep => ({ title: "", description: null, priority: "normal", offset_days: null, depends_on: [] });

export function TemplatesSheet({
  assignees,
  projects,
  customersOn,
  today,
  onClose,
  onApplied,
}: {
  assignees: Assignee[];
  projects?: { id: string; name: string }[];
  customersOn: boolean;
  today: string;
  onClose: () => void;
  onApplied: (count: number, name: string) => void;
}) {
  const [templates, setTemplates] = useState<TaskTemplate[] | null>(null);
  const [mode, setMode] = useState<Mode>({ kind: "list" });
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchTemplates()
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

  if (mode.kind === "edit") {
    return (
      <EditTemplate
        template={mode.template}
        onBack={() => setMode({ kind: "list" })}
        onSaved={() => {
          setMode({ kind: "list" });
          setVersion((value) => value + 1);
        }}
      />
    );
  }
  if (mode.kind === "apply") {
    return (
      <ApplyTemplate
        template={mode.template}
        assignees={assignees}
        projects={projects}
        customersOn={customersOn}
        today={today}
        onBack={() => setMode({ kind: "list" })}
        onApplied={(count) => onApplied(count, mode.template.name)}
      />
    );
  }

  return (
    <Sheet
      title="Görev şablonları"
      description="Tekrarlanan işleri adımları ve sıralarıyla bir kez tanımlayın; bir müşteriye, siparişe veya projeye tek tıkla uygulayın."
      onClose={onClose}
      footer={
        <Button onClick={() => setMode({ kind: "edit", template: null })}>
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
          Henüz şablon yok. Örneğin “Yeni müşteri açılışı”: karşılama araması, fiyat listesi gönderimi, iki gün sonra takip. Her adımın teslim günü uygulama tarihine göre hesaplanır.
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
                    {template.items.length} adım · {template.items.map((step) => step.title).join(" → ")}
                  </p>
                </div>
                <div className="flex shrink-0 gap-1.5">
                  <Button size="sm" variant="quiet" onClick={() => setMode({ kind: "edit", template })}>
                    Düzenle
                  </Button>
                  <Button size="sm" onClick={() => setMode({ kind: "apply", template })}>
                    Uygula
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

function EditTemplate({ template, onBack, onSaved }: { template: TaskTemplate | null; onBack: () => void; onSaved: () => void }) {
  const [name, setName] = useState(template?.name ?? "");
  const [steps, setSteps] = useState<TemplateStep[]>(template?.items.length ? template.items : [blankStep(), blankStep()]);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<"save" | "delete" | null>(null);

  function update(index: number, patch: Partial<TemplateStep>) {
    setSteps((current) => current.map((step, position) => (position === index ? { ...step, ...patch } : step)));
  }

  function remove(index: number) {
    setSteps((current) =>
      current
        .filter((_, position) => position !== index)
        .map((step) => ({ ...step, depends_on: step.depends_on.filter((parent) => parent !== index).map((parent) => (parent > index ? parent - 1 : parent)) })),
    );
  }

  async function save() {
    const filled = steps.filter((step) => step.title.trim());
    if (name.trim().length < 2) return setError("Şablona en az 2 karakterlik bir ad verin.");
    if (filled.length === 0) return setError("En az bir adım yazın.");
    if (filled.length !== steps.length) return setError("Boş adımları doldurun veya kaldırın.");
    if (steps.some((step) => step.title.trim().length < 2)) return setError("Her adım en az 2 karakter olmalı.");
    setPending("save");
    setError("");
    try {
      await saveTemplate({ name: name.trim(), description: null, items: steps.map((step) => ({ ...step, title: step.title.trim() })) }, template?.id);
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
      await deleteTemplate(template.id);
      onSaved();
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Şablon silinemedi.");
      setPending(null);
    }
  }

  return (
    <Sheet
      wide
      title={template ? "Şablonu düzenle" : "Yeni görev şablonu"}
      description="Gün, şablon uygulandığı tarihten sonraki gün sayısıdır. Bir adım yalnızca kendinden önceki adımlara bağlanabilir."
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
        <Field label="Şablon adı" value={name} onValue={setName} maxLength={120} placeholder="Ör. Sipariş teslimat hazırlığı" />
        <ol className="space-y-3">
          {steps.map((step, index) => (
            <li key={index} className="grid grid-cols-[24px_minmax(0,1fr)] gap-x-2 gap-y-2 border-b border-hairline pb-3 sm:grid-cols-[24px_minmax(0,1fr)_120px_80px_32px]">
              <span className="pt-2 text-right text-[12px] tabular-nums text-slate">{index + 1}.</span>
              <input
                aria-label={`${index + 1}. adım`}
                value={step.title}
                onChange={(event) => update(index, { title: event.target.value })}
                maxLength={200}
                placeholder="Adım"
                className={control}
              />
              <select
                aria-label={`${index + 1}. adım önceliği`}
                value={step.priority}
                onChange={(event) => update(index, { priority: event.target.value as TaskPriority })}
                className={`${control} col-start-2 sm:col-start-auto`}
              >
                {priorities.map((priority) => (
                  <option key={priority} value={priority}>
                    {priorityLabels[priority]}
                  </option>
                ))}
              </select>
              <label className="col-start-2 flex items-center gap-1.5 sm:col-start-auto">
                <span className="text-[12px] text-slate">Gün</span>
                <input
                  aria-label={`${index + 1}. adım teslim günü`}
                  type="number"
                  min={0}
                  max={365}
                  value={step.offset_days ?? ""}
                  onChange={(event) => update(index, { offset_days: event.target.value === "" ? null : Math.max(0, Math.min(365, Number(event.target.value))) })}
                  className={control}
                />
              </label>
              <button
                type="button"
                aria-label={`${index + 1}. adımı kaldır`}
                onClick={() => remove(index)}
                disabled={steps.length === 1}
                className="col-start-2 grid h-9 w-8 place-items-center justify-self-end rounded-md text-slate hover:bg-midnight/[0.05] hover:text-error-text disabled:opacity-30 sm:col-start-auto"
              >
                <Icon name="trash" className="h-4 w-4" />
              </button>
              {index > 0 ? (
                <div className="col-start-2 flex flex-wrap items-center gap-1.5 sm:col-span-4">
                  <span className="text-[12px] text-slate">Önce bitmeli:</span>
                  {steps.slice(0, index).map((parent, parentIndex) => {
                    const on = step.depends_on.includes(parentIndex);
                    return (
                      <button
                        key={parentIndex}
                        type="button"
                        aria-pressed={on}
                        onClick={() => update(index, { depends_on: on ? step.depends_on.filter((value) => value !== parentIndex) : [...step.depends_on, parentIndex].sort() })}
                        className={`h-6 max-w-[180px] truncate rounded px-2 text-[11.5px] ring-1 ring-inset transition-colors ${
                          on ? "bg-midnight text-onink ring-midnight" : "bg-surface text-slate ring-mist hover:text-graphite"
                        }`}
                      >
                        {parentIndex + 1}. {parent.title || "adım"}
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </li>
          ))}
        </ol>
        <Button variant="quiet" size="sm" onClick={() => setSteps((current) => [...current, blankStep()])} disabled={steps.length >= 30}>
          <Icon name="plus" className="h-3.5 w-3.5" /> Adım ekle
        </Button>
      </div>
    </Sheet>
  );
}

function ApplyTemplate({
  template,
  assignees,
  projects,
  customersOn,
  today,
  onBack,
  onApplied,
}: {
  template: TaskTemplate;
  assignees: Assignee[];
  projects?: { id: string; name: string }[];
  customersOn: boolean;
  today: string;
  onBack: () => void;
  onApplied: (count: number) => void;
}) {
  const [start, setStart] = useState(today);
  const [assignee, setAssignee] = useState(assignees.find((person) => person.me)?.id ?? "");
  const [customer, setCustomer] = useState<PickerOption | null>(null);
  const [project, setProject] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  const searchCustomers = useCallback(async (q: string) => {
    const page = await fetchCustomers({ q, pageSize: 8, sort: "name" });
    return page.items.map((item) => ({ id: item.id, label: item.name, meta: item.email ?? undefined }));
  }, []);

  async function apply() {
    setPending(true);
    setError("");
    try {
      const created = await applyTemplate(template.id, {
        start_date: start || null,
        assignee_id: assignee || null,
        customer_id: customer?.id ?? null,
        order_id: null,
        project_id: project || null,
        once_per_record: true,
      });
      onApplied(created.length);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Şablon uygulanamadı.");
      setPending(false);
    }
  }

  return (
    <Sheet
      title={`“${template.name}” uygula`}
      description={`${template.items.length} görev oluşturulur. Aynı şablon aynı müşteriye veya projeye ikinci kez uygulanmaz.`}
      busy={pending}
      onClose={onBack}
      footer={
        <>
          <Button variant="quiet" onClick={onBack} disabled={pending}>
            Geri
          </Button>
          <Button onClick={() => void apply()} pending={pending} pendingLabel="Oluşturuluyor">
            {template.items.length} görevi oluştur
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="text-[13px] font-medium">Başlangıç tarihi</span>
            <input type="date" value={start} onChange={(event) => setStart(event.target.value)} className={`${control} mt-1.5`} />
          </label>
          <label className="block">
            <span className="text-[13px] font-medium">Sorumlu</span>
            <select value={assignee} onChange={(event) => setAssignee(event.target.value)} className={`${control} mt-1.5`}>
              <option value="">Atanmamış</option>
              {assignees.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.me ? `${person.name} (siz)` : person.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        {customersOn ? <Picker label="Müşteri" value={customer} onChange={setCustomer} search={searchCustomers} placeholder="Müşteriye bağla (isteğe bağlı)" /> : null}
        {projects ? (
          <label className="block">
            <span className="text-[13px] font-medium">Proje</span>
            <select value={project} onChange={(event) => setProject(event.target.value)} className={`${control} mt-1.5`}>
              <option value="">Projesiz</option>
              {projects.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <ol className="space-y-1.5 border-t border-hairline pt-4 text-[13px]">
          {template.items.map((step, index) => (
            <li key={index} className="flex justify-between gap-3">
              <span>
                <span className="tabular-nums text-slate">{index + 1}.</span> {step.title}
                {step.depends_on.length > 0 ? <span className="text-slate"> · {step.depends_on.map((parent) => parent + 1).join(", ")}. adımdan sonra</span> : null}
              </span>
              <span className="shrink-0 tabular-nums text-slate">{step.offset_days !== null ? `+${step.offset_days} gün` : "tarihsiz"}</span>
            </li>
          ))}
        </ol>
      </div>
    </Sheet>
  );
}
