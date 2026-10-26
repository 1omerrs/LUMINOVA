import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { AuthLayout } from "../components/account/AuthLayout.tsx";
import { CodeVerification, VerifiedNotice } from "../components/account/CodeVerification.tsx";
import { Alert, Button, Field, PasswordField, TextArea } from "../components/forms/Controls.tsx";
import { Icon } from "../components/ui/Icon.tsx";
import { ApiRequestError, previewJoinCode, registerAccount, registerMember, sectorOptions, teamSizeOptions, type RegisterResult } from "../lib/auth.ts";
import { emailPattern, passwordStrength } from "../lib/validation.ts";

type Kind = "manager" | "member";
type FormKey = "first_name" | "last_name" | "email" | "password" | "company_name" | "sector" | "team_size" | "join_code" | "position" | "note";
type Errors = Partial<Record<FormKey, string>>;

const empty: Record<FormKey, string> = { first_name: "", last_name: "", email: "", password: "", company_name: "", sector: "", team_size: "", join_code: "", position: "", note: "" };
const order: FormKey[] = ["join_code", "first_name", "last_name", "email", "password", "company_name", "sector", "team_size", "position", "note"];
const strengthLabels = ["", "Yetersiz", "Yeterli", "Güçlü"];
const selectClass =
  "mt-1.5 h-11 w-full rounded-lg border bg-surface px-3 text-[15px] text-graphite outline-none hover:border-stone focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)]";

function cleanCode(value: string): string {
  const raw = value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 8);
  return raw.length > 4 ? `${raw.slice(0, 4)}-${raw.slice(4)}` : raw;
}

function validate(form: Record<FormKey, string>, kind: Kind): Errors {
  const errors: Errors = {};
  if (kind === "member" && form.join_code.replace("-", "").length !== 8) errors.join_code = "Yöneticinizin verdiği 8 karakterlik kodu girin.";
  if (!form.first_name.trim()) errors.first_name = "Adınızı girin.";
  if (!form.last_name.trim()) errors.last_name = "Soyadınızı girin.";
  if (!form.email.trim()) errors.email = "E-posta adresinizi girin.";
  else if (!emailPattern.test(form.email.trim())) errors.email = "Geçerli bir e-posta adresi girin.";
  if (!form.password) errors.password = "Bir şifre belirleyin.";
  else if (form.password.length < 10) errors.password = "Şifre en az 10 karakter olmalı.";
  else if (form.password.toLowerCase() === form.email.trim().toLowerCase()) errors.password = "Şifre e-posta adresiyle aynı olamaz.";
  if (kind === "manager" && form.company_name.trim().length < 2) errors.company_name = "Şirket adı en az 2 karakter olmalı.";
  return errors;
}

export function RegisterPage() {
  const [params] = useSearchParams();
  const invitedCode = cleanCode(params.get("kod") ?? "");
  const formRef = useRef<HTMLFormElement>(null);
  const [kind, setKind] = useState<Kind | null>(invitedCode ? "member" : null);
  const [form, setForm] = useState({ ...empty, join_code: invitedCode });
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState("");
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<RegisterResult | null>(null);
  const [verified, setVerified] = useState(false);
  const [company, setCompany] = useState<{ code: string; name: string | null; error: string } | null>(null);
  const strength = passwordStrength(form.password);

  useEffect(() => {
    const code = form.join_code;
    if (kind !== "member" || code.replace("-", "").length !== 8) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      previewJoinCode(code)
        .then((name) => {
          if (!cancelled) setCompany({ code, name, error: "" });
        })
        .catch((caught: unknown) => {
          if (!cancelled) setCompany({ code, name: null, error: caught instanceof ApiRequestError ? caught.message : "Kod doğrulanamadı." });
        });
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [form.join_code, kind]);

  function update(key: FormKey, value: string) {
    setForm((current) => ({ ...current, [key]: key === "join_code" ? cleanCode(value) : value }));
    if (errors[key]) setErrors((current) => ({ ...current, [key]: undefined }));
  }

  function focusFirst(next: Errors) {
    const first = order.find((key) => next[key]);
    if (first) formRef.current?.querySelector<HTMLElement>(`[name="${first}"]`)?.focus();
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!kind) return;
    setFormError("");
    const local = validate(form, kind);
    if (Object.keys(local).length > 0) {
      setErrors(local);
      focusFirst(local);
      return;
    }
    setPending(true);
    try {
      const base = { first_name: form.first_name, last_name: form.last_name, email: form.email.trim(), password: form.password };
      setResult(
        kind === "manager"
          ? await registerAccount({ ...base, company_name: form.company_name, sector: form.sector || null, team_size: form.team_size || null })
          : await registerMember({ ...base, join_code: form.join_code, position: form.position, note: form.note }),
      );
    } catch (error) {
      if (error instanceof ApiRequestError) {
        const fields = error.fields as Errors;
        if (Object.keys(fields).length > 0) {
          setErrors(fields);
          focusFirst(fields);
        } else if (error.status === 409) {
          setErrors({ email: error.message });
          focusFirst({ email: error.message });
        } else if (error.status === 404 && kind === "member") {
          setErrors({ join_code: error.message });
          focusFirst({ join_code: error.message });
        } else {
          setFormError(error.status === 0 ? "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip tekrar deneyin." : error.message);
        }
      } else {
        setFormError("Hesap oluşturulamadı. Lütfen tekrar deneyin.");
      }
    } finally {
      setPending(false);
    }
  }

  const footer = (
    <>
      Zaten hesabınız var mı?{" "}
      <Link to="/giris" className="font-semibold text-violet hover:underline">
        Giriş yapın
      </Link>
    </>
  );

  if (result && verified) {
    return <VerifiedNotice email={form.email.trim()} joining={kind === "member"} />;
  }

  if (result) {
    return (
      <AuthLayout
        variant="register"
        step={2}
        joining={kind === "member"}
        eyebrow={kind === "member" ? "KATILIM İSTEĞİ ALINDI" : "HESAP OLUŞTURULDU"}
        title="E-postanızı doğrulayın."
        description={`${form.email.trim()} adresine 6 haneli bir kod gönderdik. Kod 30 dakika geçerlidir.`}
        footer={
          <>
            E-posta adresini yanlış mı yazdınız?{" "}
            <button
              type="button"
              onClick={() => {
                setResult(null);
                setForm((current) => ({ ...current, password: "" }));
              }}
              className="font-semibold text-violet hover:underline"
            >
              Yeniden kayıt olun
            </button>
          </>
        }
      >
        <div className="mb-5 flex items-start gap-3 rounded-xl bg-cloud px-4 py-3.5">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-surface text-violet ring-1 ring-mist">
            <Icon name="mail" className="h-[18px] w-[18px]" />
          </span>
          <p className="text-[13px] leading-5 text-slate">{result.message}</p>
        </div>
        <CodeVerification email={form.email.trim()} onVerified={() => setVerified(true)} />
        {result.verification_path ? (
          <p className="mt-4 text-center text-[12px] text-slate">
            Yerel geliştirme:{" "}
            <Link to={result.verification_path} className="font-medium text-violet hover:underline">
              kodsuz doğrula
            </Link>
          </p>
        ) : null}
      </AuthLayout>
    );
  }

  if (!kind) {
    return (
      <AuthLayout
        variant="register"
        step={1}
        eyebrow="HESAP OLUŞTUR"
        title="LUMINOVA'yı nasıl kullanacaksınız?"
        description="Şirketiniz için yeni bir çalışma alanı kurabilir veya yöneticinizin verdiği katılım koduyla ekibinize katılabilirsiniz."
        footer={footer}
      >
        <div className="space-y-3">
          {(
            [
              { value: "manager", icon: "home", title: "Şirketimi kuruyorum", body: "Yönetici olarak çalışma alanı açarım, modülleri seçerim ve ekibimi eklerim." },
              { value: "member", icon: "user", title: "Bir ekibe katılıyorum", body: "Yöneticimin verdiği katılım koduyla kayıt olurum; yönetici onaylayınca giriş yaparım." },
            ] as const
          ).map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setKind(option.value)}
              className="flex w-full items-start gap-4 rounded-2xl border border-mist bg-surface px-5 py-4 text-left transition-colors hover:border-violet/60 hover:bg-violet/[0.03] focus-visible:border-violet focus-visible:outline-none"
            >
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-cloud text-violet ring-1 ring-inset ring-mist">
                <Icon name={option.icon} className="h-5 w-5" />
              </span>
              <span>
                <span className="block text-[15px] font-semibold">{option.title}</span>
                <span className="mt-0.5 block text-[13px] leading-5 text-slate">{option.body}</span>
              </span>
            </button>
          ))}
        </div>
      </AuthLayout>
    );
  }

  const preview = company && company.code === form.join_code ? company : null;
  return (
    <AuthLayout
      variant="register"
      step={1}
      joining={kind === "member"}
      eyebrow={kind === "manager" ? "YENİ ÇALIŞMA ALANI" : "EKİBE KATIL"}
      title={kind === "manager" ? "İşletmenizi kendi düzeninizde yönetin." : "Ekibinize katılın."}
      description={
        kind === "manager"
          ? "Çalışma alanınızı oluşturun; modülleri ve ekip arkadaşlarınızın yetkilerini siz belirleyin."
          : "Yöneticinizin paylaştığı katılım kodunu girin. Kaydınız yöneticinizin onayına gider."
      }
      footer={footer}
    >
      <form ref={formRef} className="space-y-4" onSubmit={(event) => void onSubmit(event)} noValidate>
        <button type="button" onClick={() => setKind(null)} className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-violet hover:underline">
          <Icon name="chevron-left" className="h-3.5 w-3.5" />
          {kind === "manager" ? "Yönetici olarak kayıt" : "Ekip üyesi olarak kayıt"} · değiştir
        </button>
        {kind === "member" ? (
          <div>
            <Field
              label="Katılım kodu"
              name="join_code"
              autoComplete="off"
              placeholder="ABCD-1234"
              value={form.join_code}
              error={errors.join_code ?? (preview?.error || undefined)}
              onValue={(value) => update("join_code", value)}
            />
            {preview?.name ? (
              <p className="mt-1.5 flex items-center gap-1.5 text-[13px] text-success-text">
                <Icon name="check" className="h-4 w-4" /> {preview.name} ekibine katılma isteği göndereceksiniz.
              </p>
            ) : null}
          </div>
        ) : null}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Ad" name="first_name" autoComplete="given-name" value={form.first_name} error={errors.first_name} onValue={(value) => update("first_name", value)} />
          <Field label="Soyad" name="last_name" autoComplete="family-name" value={form.last_name} error={errors.last_name} onValue={(value) => update("last_name", value)} />
        </div>
        <Field label="E-posta adresi" name="email" type="email" inputMode="email" autoComplete="email" placeholder="ad@sirketiniz.com" value={form.email} error={errors.email} onValue={(value) => update("email", value)} />
        <PasswordField
          label="Şifre"
          name="password"
          autoComplete="new-password"
          value={form.password}
          error={errors.password}
          onValue={(value) => update("password", value)}
          hint={
            <span className="flex items-center gap-3">
              <span className="flex gap-1" aria-hidden>
                {[1, 2, 3].map((level) => (
                  <span key={level} className={`h-1 w-7 rounded-full transition-colors ${strength >= level ? (strength === 1 ? "bg-warning" : "bg-violet") : "bg-mist"}`} />
                ))}
              </span>
              <span>{strength === 0 ? "En az 10 karakter kullanın." : `${strengthLabels[strength]} · en az 10 karakter`}</span>
            </span>
          }
        />
        {kind === "manager" ? (
          <>
            <Field label="Şirket adı" name="company_name" autoComplete="organization" value={form.company_name} error={errors.company_name} onValue={(value) => update("company_name", value)} />
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="register-sector" className="text-[13px] font-medium text-graphite">
                  Sektör
                </label>
                <select id="register-sector" name="sector" value={form.sector} onChange={(event) => update("sector", event.target.value)} className={`${selectClass} border-mist`}>
                  <option value="">Seçin (isteğe bağlı)</option>
                  {sectorOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="register-size" className="text-[13px] font-medium text-graphite">
                  Ekip büyüklüğü
                </label>
                <select id="register-size" name="team_size" value={form.team_size} onChange={(event) => update("team_size", event.target.value)} className={`${selectClass} border-mist`}>
                  <option value="">Seçin (isteğe bağlı)</option>
                  {teamSizeOptions.map((option) => (
                    <option key={option} value={option}>
                      {option === "1" ? "Yalnızca ben" : `${option} kişi`}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </>
        ) : (
          <>
            <Field label="Göreviniz (isteğe bağlı)" name="position" autoComplete="organization-title" placeholder="Örn. Depo sorumlusu" value={form.position} onValue={(value) => update("position", value)} />
            <TextArea label="Yöneticinize not (isteğe bağlı)" name="note" rows={2} maxLength={300} value={form.note} onValue={(value) => update("note", value)} />
          </>
        )}
        {formError ? <Alert tone="error">{formError}</Alert> : null}
        <Button type="submit" size="lg" className="mt-2 w-full" pending={pending} pendingLabel={kind === "manager" ? "Hesabınız oluşturuluyor" : "İsteğiniz gönderiliyor"}>
          {kind === "manager" ? "Çalışma alanını oluştur" : "Katılım isteği gönder"}
        </Button>
      </form>
    </AuthLayout>
  );
}
