import { useEffect, useState, type FormEvent } from "react";
import { createCustomer, fetchMatches, phonePattern, updateCustomer, type Customer, type CustomerDraft, type CustomerMatch } from "../../lib/customers.ts";
import { ApiRequestError } from "../../lib/http.ts";
import { emailPattern } from "../../lib/validation.ts";
import { Alert, Button, Field, TextArea } from "../forms/Controls.tsx";
import { Sheet } from "../ui/Sheet.tsx";

type Errors = Partial<Record<keyof CustomerDraft, string>>;

const order: (keyof CustomerDraft)[] = ["name", "email", "phone", "note"];

function validate(draft: CustomerDraft): Errors {
  const errors: Errors = {};
  if (draft.name.trim().length < 2) errors.name = "Müşteri adı en az 2 karakter olmalı.";
  if (draft.email.trim() && !emailPattern.test(draft.email.trim())) errors.email = "Geçerli bir e-posta adresi girin.";
  if (draft.phone.trim() && (!phonePattern.test(draft.phone.trim()) || draft.phone.replace(/\D/g, "").length < 7)) {
    errors.phone = "Geçerli bir telefon numarası girin.";
  }
  if (draft.note.length > 1000) errors.note = "Not en fazla 1000 karakter olabilir.";
  return errors;
}

export function CustomerEditor({
  customer,
  onClose,
  onSaved,
  onOpenExisting,
}: {
  customer: Customer | null;
  onClose: () => void;
  onSaved: (customer: Customer, created: boolean) => void;
  onOpenExisting?: (id: string) => void;
}) {
  const [draft, setDraft] = useState<CustomerDraft>({
    name: customer?.name ?? "",
    email: customer?.email ?? "",
    phone: customer?.phone ?? "",
    note: customer?.note ?? "",
  });
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState("");
  const [pending, setPending] = useState(false);
  const [matches, setMatches] = useState<{ key: string; items: CustomerMatch[] }>({ key: "", items: [] });
  const matchKey = `${draft.name.trim()}|${draft.email.trim()}|${draft.phone.trim()}`;

  useEffect(() => {
    if (draft.name.trim().length < 3 && !draft.email.trim() && draft.phone.replace(/\D/g, "").length < 7) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      fetchMatches(draft, customer?.id)
        .then((items) => {
          if (!cancelled) setMatches({ key: matchKey, items });
        })
        .catch(() => undefined);
    }, 350);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [matchKey, draft, customer?.id]);

  const shown = matches.key === matchKey ? matches.items : [];

  function update(key: keyof CustomerDraft, value: string) {
    setDraft((current) => ({ ...current, [key]: value }));
    if (errors[key]) setErrors((current) => ({ ...current, [key]: undefined }));
  }

  function focusFirst(form: HTMLFormElement, next: Errors) {
    const first = order.find((key) => next[key]);
    if (first) form.querySelector<HTMLElement>(`[name="${first}"]`)?.focus();
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setFormError("");
    const local = validate(draft);
    setErrors(local);
    if (Object.keys(local).length > 0) {
      focusFirst(form, local);
      return;
    }
    setPending(true);
    try {
      const saved = customer ? await updateCustomer(customer.id, draft) : await createCustomer(draft);
      onSaved(saved, customer === null);
    } catch (error) {
      if (error instanceof ApiRequestError && error.status === 409) {
        setErrors({ email: error.message });
        focusFirst(form, { email: error.message });
      } else if (error instanceof ApiRequestError && Object.keys(error.fields).length > 0) {
        setErrors(error.fields as Errors);
        focusFirst(form, error.fields as Errors);
      } else {
        setFormError(error instanceof ApiRequestError ? error.message : "Müşteri kaydedilemedi.");
      }
      setPending(false);
    }
  }

  return (
    <Sheet
      title={customer ? "Müşteriyi düzenle" : "Yeni müşteri"}
      description={customer ? customer.name : "Yalnızca müşteri adı zorunludur."}
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
            {customer ? "Değişiklikleri kaydet" : "Müşteriyi ekle"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label="Müşteri adı veya unvanı" name="name" autoComplete="organization" value={draft.name} error={errors.name} onValue={(value) => update("name", value)} />
        <Field label="E-posta adresi" name="email" type="email" inputMode="email" autoComplete="off" value={draft.email} error={errors.email} onValue={(value) => update("email", value)} />
        <Field
          label="Telefon"
          name="phone"
          type="tel"
          inputMode="tel"
          autoComplete="off"
          placeholder="+90 5xx xxx xx xx"
          value={draft.phone}
          error={errors.phone}
          onValue={(value) => update("phone", value)}
        />
        {shown.length > 0 ? (
          <div role="status" className="rounded-lg border border-warning/30 bg-warning/[0.06] px-3.5 py-3">
            <p className="text-[13px] font-medium text-warning-text">Bu müşteri zaten kayıtlı olabilir</p>
            <ul className="mt-1.5 space-y-1">
              {shown.map((match) => (
                <li key={match.id} className="flex items-center justify-between gap-3 text-[13px]">
                  <span className="min-w-0 truncate">
                    <span className="font-medium">{match.name}</span>
                    <span className="text-slate"> · {match.reason}</span>
                  </span>
                  {onOpenExisting ? (
                    <button type="button" onClick={() => onOpenExisting(match.id)} className="shrink-0 text-[12.5px] font-medium text-graphite underline underline-offset-2">
                      Kaydı aç
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
            <p className="mt-1.5 text-[12px] text-slate">Farklı bir müşteriyse kaydetmeye devam edebilirsiniz.</p>
          </div>
        ) : null}
        <TextArea label="Not" name="note" maxLength={1000} value={draft.note} error={errors.note} onValue={(value) => update("note", value)} hint="Yalnızca çalışma alanınızdaki kişiler görür." />
        {formError ? <Alert tone="error">{formError}</Alert> : null}
      </div>
    </Sheet>
  );
}
