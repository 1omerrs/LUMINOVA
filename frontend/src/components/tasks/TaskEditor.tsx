import { useCallback, useState, type FormEvent } from "react";
import { fetchCustomers } from "../../lib/customers.ts";
import { ApiRequestError } from "../../lib/http.ts";
import {
  addDays,
  createTask,
  fetchTasks,
  setDependencies,
  type TaskRef,
  priorities,
  priorityLabels,
  statuses,
  statusLabels,
  updateTask,
  type Assignee,
  type Task,
  type TaskPayload,
  type TaskPriority,
  type TaskStatus,
} from "../../lib/tasks.ts";
import { Alert, Button, Field, TextArea } from "../forms/Controls.tsx";
import { quickCustomer } from "../../lib/quickCreate.ts";
import { Picker, type PickerOption } from "../forms/Picker.tsx";
import { Icon } from "../ui/Icon.tsx";
import { Sheet } from "../ui/Sheet.tsx";

const selectClass =
  "mt-1.5 h-11 w-full rounded-lg border border-mist bg-surface px-3 text-[15px] text-graphite outline-none hover:border-stone focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)]";
const chipClass = "h-8 rounded-full px-3 text-[12px] font-semibold ring-1 ring-inset transition-colors";

export function TaskEditor({
  task,
  initialStatus = "todo",
  initialProject = null,
  assignees,
  projects,
  customersOn = false,
  initialCustomer = null,
  today,
  onClose,
  onSaved,
  onDelete,
}: {
  task: Task | null;
  initialStatus?: TaskStatus;
  initialProject?: string | null;
  assignees: Assignee[];
  projects?: { id: string; name: string }[];
  customersOn?: boolean;
  initialCustomer?: PickerOption | null;
  today: string;
  onClose: () => void;
  onSaved: (task: Task, created: boolean) => void;
  onDelete: (task: Task) => void;
}) {
  const [draft, setDraft] = useState<TaskPayload>({
    title: task?.title ?? "",
    description: task?.description ?? "",
    status: task?.status ?? initialStatus,
    priority: task?.priority ?? "normal",
    due_date: task?.due_date ?? null,
    assignee_id: task ? task.assignee_id : (assignees.find((item) => item.me)?.id ?? null),
    project_id: task ? task.project_id : initialProject,
  });
  const [customer, setCustomer] = useState<PickerOption | null>(
    task?.customer_id && task.customer_name ? { id: task.customer_id, label: task.customer_name } : task ? null : initialCustomer,
  );
  const [prerequisites, setPrerequisites] = useState<TaskRef[]>(task?.depends_on ?? []);
  const original = (task?.depends_on ?? []).map((item) => item.id).sort().join(",");
  const waiting = prerequisites.filter((item) => item.status !== "done");

  const searchCustomers = useCallback(async (q: string) => {
    const page = await fetchCustomers({ q, pageSize: 8, sort: "name" });
    return page.items.map((item) => ({ id: item.id, label: item.name, meta: item.email ?? item.phone ?? undefined }));
  }, []);

  const searchTasks = useCallback(
    async (q: string) => {
      const page = await fetchTasks({ q, sort: "due_date", pageSize: 10 });
      const chosen = new Set(prerequisites.map((item) => item.id));
      return page.items
        .filter((item) => item.id !== task?.id && !chosen.has(item.id))
        .map((item) => ({ id: item.id, label: item.title, meta: statusLabels[item.status] }));
    },
    [prerequisites, task?.id],
  );
  const projectOptions =
    projects && task?.project_id && task.project_name && !projects.some((item) => item.id === task.project_id)
      ? [{ id: task.project_id, name: task.project_name }, ...projects]
      : projects;
  const [titleError, setTitleError] = useState("");
  const [formError, setFormError] = useState("");
  const [pending, setPending] = useState(false);
  const quickDates = [
    { label: "Bugün", value: today },
    { label: "Yarın", value: addDays(today, 1) },
    { label: "Gelecek hafta", value: addDays(today, 7) },
  ];

  function update<K extends keyof TaskPayload>(key: K, value: TaskPayload[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setFormError("");
    if (draft.title.trim().length < 2) {
      setTitleError("Görev başlığı en az 2 karakter olmalı.");
      form.querySelector<HTMLElement>('[name="title"]')?.focus();
      return;
    }
    setPending(true);
    const payload: TaskPayload = customersOn ? { ...draft, customer_id: customer?.id ?? null } : draft;
    const wanted = prerequisites.map((item) => item.id);
    const changed = wanted.slice().sort().join(",") !== original;
    try {
      let saved: Task;
      if (task) {
        if (changed) await setDependencies(task.id, wanted);
        saved = await updateTask(task.id, payload);
      } else {
        saved = await createTask({ ...payload, status: wanted.length > 0 && payload.status !== "todo" ? "todo" : payload.status });
        if (changed) saved = await setDependencies(saved.id, wanted);
      }
      onSaved(saved, task === null);
    } catch (error) {
      if (error instanceof ApiRequestError && error.fields.title) setTitleError(error.fields.title);
      else setFormError(error instanceof ApiRequestError ? error.message : "Görev kaydedilemedi.");
      setPending(false);
    }
  }

  return (
    <Sheet
      title={task ? "Görevi düzenle" : "Yeni görev"}
      description={task ? task.title : "Yalnızca başlık zorunludur."}
      busy={pending}
      onClose={onClose}
      onSubmit={(event) => void onSubmit(event)}
      initialFocus='[name="title"]'
      footer={
        <>
          {task ? (
            <Button type="button" variant="quiet" onClick={() => onDelete(task)} disabled={pending} className="mr-auto text-error-text">
              <Icon name="trash" className="h-4 w-4" />
              Sil
            </Button>
          ) : null}
          <Button type="button" variant="quiet" onClick={onClose} disabled={pending}>
            Vazgeç
          </Button>
          <Button type="submit" pending={pending} pendingLabel="Kaydediliyor">
            {task ? "Değişiklikleri kaydet" : "Görevi ekle"}
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <Field
          label="Başlık"
          name="title"
          autoComplete="off"
          maxLength={200}
          value={draft.title}
          error={titleError}
          onValue={(value) => {
            update("title", value);
            setTitleError("");
          }}
        />
        <TextArea label="Açıklama" name="description" rows={4} maxLength={4000} value={draft.description} onValue={(value) => update("description", value)} />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="task-status" className="text-[13px] font-medium text-graphite">
              Durum
            </label>
            <select id="task-status" value={draft.status} onChange={(event) => update("status", event.target.value as TaskStatus)} className={selectClass}>
              {statuses.map((status) => (
                <option key={status} value={status}>
                  {statusLabels[status]}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="task-assignee" className="text-[13px] font-medium text-graphite">
              Sorumlu
            </label>
            <select
              id="task-assignee"
              value={draft.assignee_id ?? ""}
              onChange={(event) => update("assignee_id", event.target.value || null)}
              className={selectClass}
            >
              <option value="">Atanmamış</option>
              {assignees.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.me ? `${person.name} (siz)` : person.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {projectOptions ? (
          <div>
            <label htmlFor="task-project" className="text-[13px] font-medium text-graphite">
              Proje
            </label>
            <select
              id="task-project"
              value={draft.project_id ?? ""}
              onChange={(event) => update("project_id", event.target.value || null)}
              className={selectClass}
            >
              <option value="">Projesiz</option>
              {projectOptions.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        {customersOn ? (
          <Picker label="Müşteri" value={customer} onChange={setCustomer} search={searchCustomers} create={quickCustomer} placeholder="Müşteri ara (isteğe bağlı)" emptyText="Müşteri bulunamadı." />
        ) : null}

        <div>
          <Picker
            label="Önce tamamlanması gereken görevler"
            value={null}
            onChange={(option) => {
              if (!option) return;
              setPrerequisites((current) => [...current, { id: option.id, title: option.label, status: "todo" }]);
            }}
            search={searchTasks}
            placeholder="Görev ara ve ekle"
            emptyText="Eklenebilecek görev yok."
          />
          {prerequisites.length > 0 ? (
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {prerequisites.map((item) => (
                <li key={item.id} className="inline-flex max-w-full items-center gap-1.5 rounded-md bg-paper py-1 pl-2.5 pr-1 text-[12.5px] ring-1 ring-inset ring-mist">
                  <span aria-hidden className={`h-1.5 w-1.5 shrink-0 rounded-full ${item.status === "done" ? "bg-success" : "bg-warning"}`} />
                  <span className="truncate">{item.title}</span>
                  <button
                    type="button"
                    aria-label={`“${item.title}” bağlantısını kaldır`}
                    onClick={() => setPrerequisites((current) => current.filter((other) => other.id !== item.id))}
                    className="grid h-5 w-5 place-items-center rounded text-slate hover:bg-mist/60 hover:text-graphite"
                  >
                    <Icon name="close" className="h-3 w-3" />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1.5 text-[12px] text-slate">Bağlı görevler bitmeden bu görev başlatılamaz; son bağlı görev tamamlanınca kendiliğinden açılır.</p>
          )}
          {waiting.length > 0 && draft.status !== "todo" ? (
            <p className="mt-1.5 text-[12px] text-warning-text">Bekleyen {waiting.length} görev tamamlanmadan durum “{statusLabels[draft.status]}” olarak kaydedilemez.</p>
          ) : null}
        </div>

        <fieldset>
          <legend className="text-[13px] font-medium text-graphite">Öncelik</legend>
          <div className="mt-2 grid grid-cols-4 gap-1 rounded-xl bg-cloud p-1">
            {priorities.map((priority) => (
              <label key={priority} className="relative">
                <input
                  type="radio"
                  name="priority"
                  value={priority}
                  checked={draft.priority === priority}
                  onChange={() => update("priority", priority as TaskPriority)}
                  className="peer sr-only"
                />
                <span className="flex h-9 cursor-pointer items-center justify-center rounded-[9px] text-[13px] font-semibold text-slate transition-colors hover:text-graphite peer-checked:bg-surface peer-checked:text-graphite peer-checked:shadow-[0_1px_3px_rgba(16,19,28,0.12)] peer-focus-visible:outline-2 peer-focus-visible:outline-violet">
                  {priority === "urgent" || priority === "high" ? (
                    <span aria-hidden className={`mr-1.5 h-1.5 w-1.5 rounded-full ${priority === "urgent" ? "bg-error" : "bg-warning"}`} />
                  ) : null}
                  {priorityLabels[priority]}
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <div>
          <label htmlFor="task-due" className="text-[13px] font-medium text-graphite">
            Teslim tarihi
          </label>
          <input
            id="task-due"
            type="date"
            value={draft.due_date ?? ""}
            onChange={(event) => update("due_date", event.target.value || null)}
            className={selectClass}
          />
          <div className="mt-2 flex flex-wrap gap-1.5">
            {quickDates.map((item) => (
              <button
                key={item.label}
                type="button"
                aria-pressed={draft.due_date === item.value}
                onClick={() => update("due_date", item.value)}
                className={`${chipClass} ${draft.due_date === item.value ? "bg-violet/10 text-violet ring-violet/30" : "bg-surface text-slate ring-mist hover:text-graphite"}`}
              >
                {item.label}
              </button>
            ))}
            {draft.due_date ? (
              <button type="button" onClick={() => update("due_date", null)} className={`${chipClass} bg-surface text-slate ring-mist hover:text-graphite`}>
                Tarihi kaldır
              </button>
            ) : null}
          </div>
        </div>

        {formError ? <Alert tone="error">{formError}</Alert> : null}
      </div>
    </Sheet>
  );
}
