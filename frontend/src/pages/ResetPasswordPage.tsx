import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { AuthLayout } from "../components/account/AuthLayout.tsx";
import { Alert, Button, PasswordField } from "../components/forms/Controls.tsx";
import { Icon } from "../components/ui/Icon.tsx";
import { ApiRequestError, resetPassword } from "../lib/auth.ts";

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<{ password?: string; confirm?: string }>({});
  const [formError, setFormError] = useState(token ? "" : "Sıfırlama bağlantısında belirteç bulunamadı.");
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState("");

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    const next: typeof errors = {};
    if (password.length < 10) next.password = "Şifre en az 10 karakter olmalı.";
    if (confirm !== password) next.confirm = "Şifreler eşleşmiyor.";
    setErrors(next);
    if (next.password || next.confirm) {
      return;
    }
    setPending(true);
    try {
      setDone(await resetPassword(token, password));
    } catch (error) {
      setFormError(error instanceof ApiRequestError ? error.message : "Şifre güncellenemedi.");
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthLayout
      variant="login"
      eyebrow="ŞİFRE SIFIRLAMA"
      title={done ? "Şifreniz güncellendi." : "Yeni şifrenizi belirleyin."}
      description={done ? "Güvenliğiniz için açık oturumlarınız kapatıldı." : "Yeni şifreniz en az 10 karakter olmalı."}
    >
      {done ? (
        <div className="space-y-5">
          <Alert tone="success">{done}</Alert>
          <Link
            to="/giris"
            className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-violet text-[15px] font-semibold text-white transition-colors hover:bg-[#4636b5]"
          >
            Giriş yap
            <Icon name="arrow-right" className="h-4 w-4" />
          </Link>
        </div>
      ) : (
        <form className="space-y-4" onSubmit={(event) => void onSubmit(event)} noValidate>
          <PasswordField label="Yeni şifre" name="password" autoComplete="new-password" value={password} error={errors.password} onValue={setPassword} />
          <PasswordField label="Yeni şifre (tekrar)" name="confirm" autoComplete="new-password" value={confirm} error={errors.confirm} onValue={setConfirm} />
          {formError ? <Alert tone="error">{formError}</Alert> : null}
          <Button type="submit" size="lg" className="w-full" pending={pending} pendingLabel="Güncelleniyor" disabled={!token}>
            Şifremi güncelle
          </Button>
          <p className="text-center text-[14px] text-slate">
            Bağlantının süresi dolduysa{" "}
            <Link to="/sifremi-unuttum" className="font-semibold text-violet hover:underline">
              yeni bağlantı isteyin
            </Link>
            .
          </p>
        </form>
      )}
    </AuthLayout>
  );
}
