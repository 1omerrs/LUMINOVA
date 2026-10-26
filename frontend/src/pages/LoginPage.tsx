import { useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { AuthLayout } from "../components/account/AuthLayout.tsx";
import { Alert, Button, Checkbox, Field, PasswordField } from "../components/forms/Controls.tsx";
import { ApiRequestError, loginAccount } from "../lib/auth.ts";
import { emailPattern } from "../lib/validation.ts";

type Errors = { email?: string; password?: string };

export function LoginPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const formRef = useRef<HTMLFormElement>(null);
  const [email, setEmail] = useState(() => params.get("eposta") ?? "");
  const [needsCode, setNeedsCode] = useState(false);
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState("");
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    setNeedsCode(false);
    const local: Errors = {};
    if (!email.trim()) local.email = "E-posta adresinizi girin.";
    else if (email.includes("@") && !emailPattern.test(email.trim())) local.email = "Geçerli bir e-posta adresi girin.";
    if (!password) local.password = "Şifrenizi girin.";
    setErrors(local);
    if (local.email || local.password) {
      formRef.current?.querySelector<HTMLInputElement>(`[name="${local.email ? "email" : "password"}"]`)?.focus();
      return;
    }

    setPending(true);
    try {
      const user = await loginAccount(email.trim(), password, remember);
      await navigate(user.staff_only ? "/yonetim" : user.setup_completed ? "/panel" : "/kurulum", { replace: true });
    } catch (error) {
      if (error instanceof ApiRequestError) {
        setNeedsCode(error.status === 403 && error.message.includes("doğrulamanız gerekiyor"));
        setFormError(
          error.status === 0
            ? "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip tekrar deneyin."
            : error.status === 401
              ? `${error.message} Kayıt olurken kullandığınız e-posta adresini yazdığınızdan emin olun.`
              : error.message,
        );
      } else {
        setFormError("Giriş yapılamadı. Lütfen tekrar deneyin.");
      }
      setPending(false);
    }
  }

  return (
    <AuthLayout
      variant="login"
      title="Tekrar hoş geldiniz."
      description="Çalışma alanınıza giriş yapın ve iş süreçlerinizi yönetmeye devam edin."
      footer={
        <>
          Hesabınız yok mu?{" "}
          <Link to="/kayit" className="font-semibold text-violet hover:underline">
            Hesap oluşturun
          </Link>
        </>
      }
    >
      <form ref={formRef} className="space-y-4" onSubmit={(event) => void onSubmit(event)} noValidate>
        {formError ? (
          <Alert tone="error">
            {formError}
            {needsCode ? (
              <>
                {" "}
                <Link to={`/dogrula?eposta=${encodeURIComponent(email.trim())}`} className="font-semibold underline">
                  Doğrulama kodunu girin
                </Link>
              </>
            ) : null}
          </Alert>
        ) : null}
        <Field
          label="E-posta adresi"
          name="email"
          type="text"
          inputMode="email"
          autoComplete="username"
          value={email}
          error={errors.email}
          onValue={(value) => {
            setEmail(value);
            setErrors((current) => ({ ...current, email: undefined }));
          }}
        />
        <PasswordField
          label="Şifre"
          name="password"
          autoComplete="current-password"
          value={password}
          error={errors.password}
          labelAction={
            <Link to="/sifremi-unuttum" className="text-[13px] font-medium text-violet hover:underline">
              Şifremi unuttum
            </Link>
          }
          onValue={(value) => {
            setPassword(value);
            setErrors((current) => ({ ...current, password: undefined }));
          }}
        />
        <div className="flex items-center justify-between pt-1">
          <Checkbox label="Beni hatırla" checked={remember} onChange={setRemember} />
          <span className="text-[12px] text-slate">{remember ? "30 gün açık kalır" : "Tarayıcı kapanınca biter"}</span>
        </div>
        <Button type="submit" size="lg" className="mt-2 w-full" pending={pending} pendingLabel="Giriş yapılıyor">
          Giriş yap
        </Button>
      </form>
    </AuthLayout>
  );
}
