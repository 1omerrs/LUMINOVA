import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { AuthLayout } from "../components/account/AuthLayout.tsx";
import { Alert, Button, Field, PasswordField, Spinner } from "../components/forms/Controls.tsx";
import { ApiRequestError } from "../lib/http.ts";
import { acceptInvitation, previewInvitation, roleLabels, type InvitationPreview } from "../lib/team.ts";

type Errors = Partial<Record<"first_name" | "last_name" | "password" | "confirm", string>>;

export function InvitePage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token") ?? "";
  const [preview, setPreview] = useState<InvitationPreview | null>(null);
  const [loadError, setLoadError] = useState(token ? "" : "Davet bağlantısında belirteç bulunamadı.");
  const [form, setForm] = useState({ first_name: "", last_name: "", password: "", confirm: "" });
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState("");
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    previewInvitation(token)
      .then((next) => {
        if (!cancelled) setPreview(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setLoadError(caught instanceof ApiRequestError ? caught.message : "Davet doğrulanamadı.");
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  function update(key: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
    setErrors((current) => ({ ...current, [key]: undefined }));
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    const next: Errors = {};
    if (!form.first_name.trim()) next.first_name = "Adınızı girin.";
    if (!form.last_name.trim()) next.last_name = "Soyadınızı girin.";
    if (form.password.length < 10) next.password = "Şifre en az 10 karakter olmalı.";
    if (form.confirm !== form.password) next.confirm = "Şifreler eşleşmiyor.";
    setErrors(next);
    if (Object.values(next).some(Boolean)) return;
    setPending(true);
    try {
      await acceptInvitation({ token, first_name: form.first_name, last_name: form.last_name, password: form.password });
      navigate("/panel", { replace: true });
    } catch (caught) {
      setFormError(caught instanceof ApiRequestError ? caught.message : "Davet kabul edilemedi.");
      setPending(false);
    }
  }

  return (
    <AuthLayout
      variant="login"
      eyebrow="EKİP DAVETİ"
      title={preview ? `${preview.company_name} sizi bekliyor.` : "Ekip davetine katılın."}
      description={
        preview
          ? `${preview.invited_by ?? "Çalışma alanı yöneticisi"} sizi ${roleLabels[preview.role].toLocaleLowerCase("tr")} olarak davet etti. Hesabınızı oluşturun.`
          : "Davet bağlantınız doğrulanıyor."
      }
    >
      {loadError ? (
        <div className="space-y-4">
          <Alert tone="error">{loadError}</Alert>
          <p className="text-[14px] text-slate">Davet eden kişiden yeni bir bağlantı isteyin.</p>
          <Link to="/giris" className="text-[14px] font-semibold text-violet hover:underline">
            Giriş sayfasına git
          </Link>
        </div>
      ) : !preview ? (
        <p role="status" className="flex items-center gap-2.5 text-[14px] text-slate">
          <Spinner className="h-4 w-4 text-violet" /> Davet kontrol ediliyor.
        </p>
      ) : (
        <form className="space-y-4" onSubmit={(event) => void onSubmit(event)} noValidate>
          <Field label="E-posta" name="email" value={preview.email} readOnly onValue={() => undefined} hint="Davet bu adrese oluşturuldu." />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Ad" name="first_name" autoComplete="given-name" value={form.first_name} error={errors.first_name} onValue={(value) => update("first_name", value)} />
            <Field label="Soyad" name="last_name" autoComplete="family-name" value={form.last_name} error={errors.last_name} onValue={(value) => update("last_name", value)} />
          </div>
          <PasswordField label="Şifre" name="password" autoComplete="new-password" value={form.password} error={errors.password} hint="En az 10 karakter." onValue={(value) => update("password", value)} />
          <PasswordField label="Şifre (tekrar)" name="confirm" autoComplete="new-password" value={form.confirm} error={errors.confirm} onValue={(value) => update("confirm", value)} />
          {formError ? <Alert tone="error">{formError}</Alert> : null}
          <Button type="submit" size="lg" className="w-full" pending={pending} pendingLabel="Hesap oluşturuluyor">
            Hesabımı oluştur ve katıl
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}
