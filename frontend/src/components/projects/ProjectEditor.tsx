import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { fetchCustomers } from "../../lib/customers.ts";
import { ApiRequestError } from "../../lib/http.ts";
import {
  createProject,
  fetchProjectTemplates,
  projectStatuses,
  projectStatusLabels,
  updateProject,
  type Project,
  type ProjectPayload,
  type ProjectStatus,
  type ProjectTemplate,
} from "../../lib/projects.ts";
import { fetchQuotes } from "../../lib/quotes.ts";
import { fetchOrders } from "../../lib/sales.ts";
import { Alert, Button, Field, TextArea } from "../forms/Controls.tsx";
import { quickCustomer } from "../../lib/quickCreate.ts";
import { Picker, type PickerOption } from "../forms/Picker.tsx";
import { Sheet } from "../ui/Sheet.tsx";

type Errors = Partial<Record<"name" | "due_date", string>>;

function today(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

const inputClass =
  "mt-1.5 h-11 w-full rounded-lg border bg-surface px-3 text-[15px] text-graphite outline-none hover:border-stone focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)]";

type Draft = Pick<ProjectPayload, "name" | "description" | "status" | "start_date" | "due_date" | "working_days_only">;
type Source = { quote?: PickerOption | null; order?: PickerOption | null };

export function ProjectEditor({
  project,
  customersOn,
  salesOn = false,
  initialCustomer = null,
  initialTemplate = null,
  initialSource = {},
  onClose,
  onSaved,
}: {
  project: Project | null;
  customersOn: boolean;
  salesOn?: boolean;
  initialCustomer?: PickerOption | null;
  initialTemplate?: ProjectTemplate | null;
  initialSource?: Source;
  onClose: () => void;
  onSaved: (project: Project, created: boolean) => void;
}) {
  const [draft, setDraft] = useState<Draft>({
    name: project?.name ?? "",
    description: project?.description ?? "",
    status: project?.status ?? "planned",
    start_date: project?.start_date ?? (initialTemplate ? today() : null),
    due_date: project?.due_date ?? null,
    working_days_only: project?.working_days_only ?? true,
  });
  const [customer, setCustomer] = useState<PickerOption | null>(
    project?.customer_id && project.customer_name ? { id: project.customer_id, label: project.customer_name } : project ? null : initialCustomer,
  );
  const [quote, setQuote] = useState<PickerOption | null>(
    project?.quote_id && project.quote_code ? { id: project.quote_id, label: project.quote_code } : project ? null : (initialSource.quote ?? null),
  );
  const [order, setOrder] = useState<PickerOption | null>(
    project?.order_id && project.order_code ? { id: project.order_id, label: project.order_code } : project ? null : (initialSource.order ?? null),
  );
  const [templates, setTemplates] = useState<ProjectTemplate[]>(initialTemplate ? [initialTemplate] : []);
  const [templateId, setTemplateId] = useState(initialTemplate?.id ?? "");
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState("");
  const [pending, setPending] = useState(false);
  const owners = useRef(new Map<string, PickerOption>());
  const template = templates.find((item) => item.id === templateId) ?? null;

  useEffect(() => {
    if (project) return;
    let cancelled = false;
    fetchProjectTemplates()
      .then((items) => {
        if (!cancelled) setTemplates(items);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [project]);

  const searchCustomers = useCallback(async (q: string) => {
    const page = await fetchCustomers({ q, pageSize: 8, sort: "name" });
    return page.items.map((item) => ({ id: item.id, label: item.name, meta: item.email ?? item.phone ?? undefined }));
  }, []);

  const searchQuotes = useCallback(async (q: string) => {
    const page = await fetchQuotes({ q, pageSize: 8 });
    return page.items.map((item) => {
      owners.current.set(item.id, { id: item.customer_id, label: item.customer_name });
      return { id: item.id, label: item.code, meta: item.customer_name };
    });
  }, []);

  const searchOrders = useCallback(async (q: string) => {
    const page = await fetchOrders({ q, pageSize: 8 });
    return page.items.map((item) => {
      owners.current.set(item.id, { id: item.customer_id, label: item.customer_name });
      return { id: item.id, label: item.code, meta: item.customer_name };
    });
  }, []);

  function linkSource(kind: "quote" | "order", option: PickerOption | null) {
    (kind === "quote" ? setQuote : setOrder)(option);
    const owner = option ? owners.current.get(option.id) : undefined;
    if (owner && !customer) setCustomer(owner);
  }

  function update<K extends keyof typeof draft>(key: K, value: (typeof draft)[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
    if (key === "name" || key === "due_date" || key === "start_date") setErrors({});
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setFormError("");
    const local: Errors = {};
    if (draft.name.trim().length < 2) local.name = "Proje adı en az 2 karakter olmalı.";
    if (draft.start_date && draft.due_date && draft.due_date < draft.start_date) local.due_date = "Teslim tarihi başlangıç tarihinden önce olamaz.";
    setErrors(local);
    if (local.name) {
      form.querySelector<HTMLElement>('[name="name"]')?.focus();
      return;
    }
    if (local.due_date) {
      form.querySelector<HTMLElement>("#project-due")?.focus();
      return;
    }
    setPending(true);
    const payload: ProjectPayload = {
      ...draft,
      customer_id: customer?.id ?? (customersOn ? null : (project?.customer_id ?? null)),
      quote_id: quote?.id ?? (customersOn ? null : (project?.quote_id ?? null)),
      order_id: order?.id ?? (salesOn ? null : (project?.order_id ?? null)),
      ...(project ? {} : { template_id: templateId || null }),
    };
    try {
      const saved = project ? await updateProject(project.id, payload) : await createProject(payload);
      onSaved(saved, project === null);
    } catch (error) {
      if (error instanceof ApiRequestError && (error.fields.name || error.fields.due_date)) {
        setErrors({ name: error.fields.name, due_date: error.fields.due_date });
      } else {
        setFormError(error instanceof ApiRequestError ? error.message : "Proje kaydedilemedi.");
      }
      setPending(false);
    }
  }

  return (
    <Sheet
      title={project ? "Projeyi düzenle" : "Yeni proje"}
      description={project ? project.name : "Yalnızca proje adı zorunludur. Şablon seçerseniz aşamalar, görevler ve tarihler kendiliğinden oluşur."}
      busy={pending}
      onClose={onClose}
      onSubmit={(event) => void onSubmit(event)}
      initialFocus='[name="name"]'
      footer={
        <>
          <Button type="button" variant="quiet" onClick={onClose} disabled={pending}>
            Vazgeç
          </Button>
          <Button type="submit" pending={pending} pendingLabel="Kaydediliyor">
            {project ? "Değişiklikleri kaydet" : "Projeyi oluştur"}
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <Field label="Proje adı" name="name" autoComplete="off" maxLength={160} value={draft.name} error={errors.name} onValue={(value) => update("name", value)} />
        {!project && templates.length > 0 ? (
          <div>
            <label htmlFor="project-template" className="text-[13px] font-medium text-graphite">
              Şablon
            </label>
            <select
              id="project-template"
              value={templateId}
              onChange={(event) => {
                setTemplateId(event.target.value);
                if (event.target.value && !draft.start_date) update("start_date", today());
              }}
              className={`${inputClass} border-mist`}
            >
              <option value="">Şablonsuz, görevleri kendim eklerim</option>
              {templates.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
            {template ? (
              <p className="mt-1.5 text-[12.5px] leading-5 text-slate">
                {template.stages.length} aşama ve {template.items.length} görev oluşturulur; plan yaklaşık {template.total_days} gün sürer. Teslim tarihini boş bırakırsanız
                plana göre doldurulur.
              </p>
            ) : null}
          </div>
        ) : null}
        {customersOn ? (
          <Picker
            label="Müşteri (isteğe bağlı)"
            name="customer"
            value={customer}
            onChange={setCustomer}
            search={searchCustomers}
            create={quickCustomer}
            placeholder="Müşteri adıyla arayın"
            emptyText="Eşleşen müşteri yok."
          />
        ) : null}
        {customersOn || salesOn ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {customersOn ? (
              <Picker
                label="Teklif (isteğe bağlı)"
                name="quote"
                value={quote}
                onChange={(option) => linkSource("quote", option)}
                search={searchQuotes}
                placeholder="TK- numarası veya müşteri"
                emptyText="Eşleşen teklif yok."
              />
            ) : null}
            {salesOn ? (
              <Picker
                label="Sipariş (isteğe bağlı)"
                name="order"
                value={order}
                onChange={(option) => linkSource("order", option)}
                search={searchOrders}
                placeholder="SP- numarası veya müşteri"
                emptyText="Eşleşen sipariş yok."
              />
            ) : null}
          </div>
        ) : null}
        <div>
          <label htmlFor="project-status" className="text-[13px] font-medium text-graphite">
            Durum
          </label>
          <select
            id="project-status"
            value={draft.status}
            onChange={(event) => update("status", event.target.value as ProjectStatus)}
            className={`${inputClass} border-mist`}
          >
            {projectStatuses.map((status) => (
              <option key={status} value={status}>
                {projectStatusLabels[status]}
              </option>
            ))}
          </select>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="project-start" className="text-[13px] font-medium text-graphite">
              Başlangıç tarihi
            </label>
            <input
              id="project-start"
              type="date"
              value={draft.start_date ?? ""}
              onChange={(event) => update("start_date", event.target.value || null)}
              className={`${inputClass} border-mist`}
            />
          </div>
          <div>
            <label htmlFor="project-due" className="text-[13px] font-medium text-graphite">
              Teslim tarihi
            </label>
            <input
              id="project-due"
              type="date"
              value={draft.due_date ?? ""}
              aria-invalid={errors.due_date ? true : undefined}
              aria-describedby={errors.due_date ? "project-due-error" : undefined}
              onChange={(event) => update("due_date", event.target.value || null)}
              className={`${inputClass} ${errors.due_date ? "border-error/70" : "border-mist"}`}
            />
            {errors.due_date ? (
              <p id="project-due-error" className="mt-1.5 text-[13px] leading-5 text-error-text">
                {errors.due_date}
              </p>
            ) : null}
          </div>
        </div>
        <label className="flex items-start gap-3 text-[14px]">
          <input
            type="checkbox"
            name="working_days_only"
            checked={draft.working_days_only}
            onChange={(event) => update("working_days_only", event.target.checked)}
            className="mt-0.5 h-4 w-4 accent-[#5b47d6]"
          />
          <span>
            <span className="font-medium">Yalnızca iş günlerini say</span>
            <span className="mt-0.5 block text-[12.5px] leading-5 text-slate">
              Görev süreleri hesaplanırken cumartesi, pazar ve sabit tarihli resmî tatiller atlanır. Dini bayramlar tarihi her yıl değiştiği için ayrıca hesaba katılmaz.
            </span>
          </span>
        </label>
        <TextArea label="Açıklama" name="description" rows={4} maxLength={2000} value={draft.description} onValue={(value) => update("description", value)} />
        {formError ? <Alert tone="error">{formError}</Alert> : null}
      </div>
    </Sheet>
  );
}
