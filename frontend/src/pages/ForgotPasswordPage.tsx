import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { AuthLayout } from "../components/account/AuthLayout.tsx";
import { Alert, Button, Field } from "../components/forms/Controls.tsx";
import { Icon } from "../components/ui/Icon.tsx";
import { ApiRequestError, requestPasswordReset, type ResetRequestResult } from "../lib/auth.ts";
import { emailPattern } from "../lib/validation.ts";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [formError, setFormError] = useState("");
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<ResetRequestResult | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    if (!emailPattern.test(email.trim())) {
      setError(email.trim() ? "Geçerli bir e-posta adresi girin." : "E-posta adresinizi girin.");
      return;
    }
    setPending(true);
    try {
      setResult(await requestPasswordReset(email.trim()));
    } catch (caught) {
      setFormError(caught instanceof ApiRequestError ? caught.message : "İstek gönderilemedi.");
    } finally {
      setPending(false);
    }
  }

  const back = (
    <Link to="/giris" className="inline-flex items-center gap-1.5 font-semibold text-violet hover:underline">
      Giriş ekranına dön
    </Link>
  );

  return (
    <AuthLayout
      variant="login"
      eyebrow="ŞİFRE SIFIRLAMA"
      title={result ? "İsteğiniz alındı." : "Şifrenizi mi unuttunuz?"}
      description={result ? "Sıfırlama bağlantısı bir saat geçerlidir ve yalnızca bir kez kullanılabilir." : "Hesabınıza bağlı e-posta adresini girin. Şifrenizi yenilemeniz için bir bağlantı hazırlayalım."}
      footer={back}
    >
      {result ? (
        <div className="space-y-5">
          <Alert tone="info">{result.message}</Alert>
          {result.reset_path ? (
            <div>
              <Link
                to={result.reset_path}
                className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-violet text-[15px] font-semibold text-white transition-colors hover:bg-[#4636b5]"
              >
                Şifremi yenile
                <Icon name="arrow-right" className="h-4 w-4" />
              </Link>
              <p className="mt-2 text-center text-[12px] text-slate">Bu bağlantı yalnızca yerel geliştirme ortamında gösterilir.</p>
            </div>
          ) : null}
        </div>
      ) : (
        <form className="space-y-4" onSubmit={(event) => void onSubmit(event)} noValidate>
          <Field
            label="E-posta adresi"
            name="email"
            type="email"
            inputMode="email"
            autoComplete="email"
            value={email}
            error={error}
            onValue={(value) => {
              setEmail(value);
              setError("");
            }}
          />
          {formError ? <Alert tone="error">{formError}</Alert> : null}
          <Button type="submit" size="lg" className="w-full" pending={pending} pendingLabel="Hazırlanıyor">
            Sıfırlama bağlantısı iste
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}
