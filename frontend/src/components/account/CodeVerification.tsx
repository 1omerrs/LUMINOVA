import { useEffect, useRef, useState, type ClipboardEvent, type FormEvent, type KeyboardEvent } from "react";
import { Link } from "react-router";
import { AuthLayout } from "./AuthLayout.tsx";
import { Alert, Button } from "../forms/Controls.tsx";
import { Icon } from "../ui/Icon.tsx";
import { ApiRequestError, resendCode, verifyCode } from "../../lib/auth.ts";

const LENGTH = 6;
const RESEND_SECONDS = 60;

export function CodeVerification({ email, onVerified, justSent = true }: { email: string; onVerified: () => void; justSent?: boolean }) {
  const inputs = useRef<(HTMLInputElement | null)[]>([]);
  const [digits, setDigits] = useState<string[]>(() => Array.from({ length: LENGTH }, () => ""));
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [wait, setWait] = useState(justSent ? RESEND_SECONDS : 0);

  useEffect(() => {
    inputs.current[0]?.focus();
  }, []);

  useEffect(() => {
    if (wait <= 0) return;
    const timer = window.setTimeout(() => setWait((current) => current - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [wait]);

  function fill(start: number, text: string) {
    const clean = text.replace(/\D/g, "").slice(0, LENGTH - start);
    if (!clean) return;
    const next = [...digits];
    for (const [offset, digit] of [...clean].entries()) next[start + offset] = digit;
    setDigits(next);
    setError("");
    inputs.current[Math.min(start + clean.length, LENGTH - 1)]?.focus();
    if (next.every(Boolean) && start + clean.length === LENGTH) void check(next.join(""));
  }

  function onKey(index: number, event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Backspace" && !digits[index] && index > 0) {
      event.preventDefault();
      setDigits((current) => current.map((digit, position) => (position === index - 1 ? "" : digit)));
      inputs.current[index - 1]?.focus();
    } else if (event.key === "ArrowLeft" && index > 0) {
      inputs.current[index - 1]?.focus();
    } else if (event.key === "ArrowRight" && index < LENGTH - 1) {
      inputs.current[index + 1]?.focus();
    }
  }

  function onPaste(index: number, event: ClipboardEvent<HTMLInputElement>) {
    event.preventDefault();
    fill(index, event.clipboardData.getData("text"));
  }

  const entered = digits.join("");

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (entered.length !== LENGTH) {
      setError("E-postanıza gelen 6 haneli kodu girin.");
      inputs.current[digits.findIndex((digit) => !digit)]?.focus();
      return;
    }
    void check(entered);
  }

  async function check(code: string) {
    if (pending) return;
    setPending(true);
    setError("");
    try {
      await verifyCode(email, code);
      onVerified();
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? (caught.status === 0 ? "Sunucuya ulaşılamadı. Bağlantınızı kontrol edin." : caught.message) : "Kod doğrulanamadı.");
      setDigits(Array.from({ length: LENGTH }, () => ""));
      inputs.current[0]?.focus();
    } finally {
      setPending(false);
    }
  }

  async function onResend() {
    setError("");
    setNotice("");
    setWait(RESEND_SECONDS);
    try {
      setNotice(await resendCode(email));
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Yeni kod istenemedi.");
    }
  }

  return (
    <form className="space-y-4" onSubmit={onSubmit} noValidate>
      <fieldset>
        <legend className="text-[13px] font-medium text-graphite">Doğrulama kodu</legend>
        <div className="mt-1.5 flex gap-2">
          {digits.map((digit, index) => (
            <input
              key={index}
              ref={(element) => {
                inputs.current[index] = element;
              }}
              aria-label={`${index + 1}. hane`}
              inputMode="numeric"
              autoComplete={index === 0 ? "one-time-code" : "off"}
              maxLength={LENGTH}
              value={digit}
              onChange={(event) => {
                const value = event.target.value.replace(/\D/g, "");
                if (!value) setDigits((current) => current.map((item, position) => (position === index ? "" : item)));
                else fill(index, digit && value.length === 2 ? value.replace(digit, "") || digit : value);
              }}
              onKeyDown={(event) => onKey(index, event)}
              onPaste={(event) => onPaste(index, event)}
              onFocus={(event) => event.target.select()}
              className={`h-12 w-full min-w-0 rounded-lg border bg-surface text-center font-display text-[20px] font-semibold text-graphite outline-none focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)] ${error ? "border-error" : "border-mist"}`}
            />
          ))}
        </div>
      </fieldset>
      {error ? <Alert tone="error">{error}</Alert> : notice ? <Alert tone="info">{notice}</Alert> : null}
      <Button type="submit" size="lg" className="w-full" pending={pending} pendingLabel="Kod kontrol ediliyor">
        E-postamı doğrula
      </Button>
      <p className="text-center text-[13px] text-slate">
        Kod gelmedi mi?{" "}
        {wait > 0 ? (
          <span>{wait} saniye sonra yeni kod isteyebilirsiniz.</span>
        ) : (
          <button type="button" onClick={() => void onResend()} className="font-semibold text-violet hover:underline">
            Yeni kod gönder
          </button>
        )}
      </p>
    </form>
  );
}

export function VerifiedNotice({ email, joining }: { email: string; joining?: boolean }) {
  const description =
    joining === undefined
      ? "Artık giriş yapabilirsiniz. Bir ekibe katılım isteği gönderdiyseniz yöneticiniz onayladıktan sonra giriş yapabilirsiniz."
      : joining
        ? "Katılım isteğiniz yöneticinize iletildi. Yöneticiniz onaylayıp yetkilerinizi verdiğinde size e-posta gelir ve giriş yapabilirsiniz."
        : "Giriş yaptıktan sonra çalışma alanınızın modüllerini seçeceksiniz.";
  return (
    <AuthLayout
      variant="register"
      step={joining ? 3 : 2}
      joining={joining}
      eyebrow="E-POSTA DOĞRULANDI"
      title={joining === false ? "Çalışma alanınız hazır." : "E-postanız doğrulandı."}
      description={description}
    >
      <Link
        to={`/giris?eposta=${encodeURIComponent(email)}`}
        className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-violet text-[15px] font-semibold text-white transition-colors hover:bg-[#4636b5]"
      >
        {joining === false ? "Giriş yap ve kuruluma geç" : "Giriş ekranına git"}
        <Icon name="arrow-right" className="h-4 w-4" />
      </Link>
    </AuthLayout>
  );
}

