import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { AuthLayout } from "../components/account/AuthLayout.tsx";
import { CodeVerification, VerifiedNotice } from "../components/account/CodeVerification.tsx";
import { Alert, Spinner } from "../components/forms/Controls.tsx";
import { Icon } from "../components/ui/Icon.tsx";
import { ApiRequestError, verifyEmail } from "../lib/auth.ts";

type State = { status: "checking" | "done" | "failed"; message: string };

export function VerifyPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const email = params.get("eposta")?.trim() ?? "";
  return token ? <LinkVerification token={token} /> : email ? <CodeEntry email={email} /> : <LinkVerification token="" />;
}

function CodeEntry({ email }: { email: string }) {
  const [verified, setVerified] = useState(false);
  if (verified) return <VerifiedNotice email={email} />;
  return (
    <AuthLayout
      variant="register"
      step={2}
      eyebrow="E-POSTA DOĞRULAMA"
      title="E-postanızı doğrulayın."
      description={`${email} adresine gelen 6 haneli kodu girin. Kodunuzun süresi dolduysa yeni kod isteyebilirsiniz.`}
      footer={
        <>
          Doğruladıktan sonra{" "}
          <Link to={`/giris?eposta=${encodeURIComponent(email)}`} className="font-semibold text-violet hover:underline">
            giriş yapın
          </Link>
          .
        </>
      }
    >
      <CodeVerification email={email} justSent={false} onVerified={() => setVerified(true)} />
    </AuthLayout>
  );
}

function LinkVerification({ token }: { token: string }) {
  const [state, setState] = useState<State>(
    token ? { status: "checking", message: "Doğrulama bağlantınız kontrol ediliyor." } : { status: "failed", message: "Doğrulama bağlantısında belirteç bulunamadı." },
  );

  useEffect(() => {
    if (!token) {
      return;
    }
    let cancelled = false;
    verifyEmail(token)
      .then((message) => {
        if (!cancelled) setState({ status: "done", message });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({ status: "failed", message: error instanceof ApiRequestError ? error.message : "Doğrulama tamamlanamadı." });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <AuthLayout
      variant="register"
      step={state.status === "done" ? 3 : 2}
      eyebrow="E-POSTA DOĞRULAMA"
      title={state.status === "done" ? "E-posta adresiniz doğrulandı." : "E-posta adresinizi doğruluyoruz."}
      description={
        state.status === "done"
          ? "Giriş yaptıktan sonra çalışma alanınıza devam edebilirsiniz."
          : "Doğrulama bağlantıları tek kullanımlıktır ve 30 dakika geçerlidir. Süresi dolduysa giriş ekranından yeni kod isteyebilirsiniz."
      }
      footer={
        state.status === "failed" ? (
          <>
            Hesabınız zaten doğrulandıysa{" "}
            <Link to="/giris" className="font-semibold text-violet hover:underline">
              giriş yapın
            </Link>
            .
          </>
        ) : null
      }
    >
      {state.status === "checking" ? (
        <p role="status" className="flex items-center gap-2.5 text-[14px] text-slate">
          <Spinner className="h-4 w-4 text-violet" /> {state.message}
        </p>
      ) : state.status === "done" ? (
        <Link
          to="/giris"
          className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-violet text-[15px] font-semibold text-white transition-colors hover:bg-[#4636b5]"
        >
          Giriş yap
          <Icon name="arrow-right" className="h-4 w-4" />
        </Link>
      ) : (
        <Alert tone="error">{state.message}</Alert>
      )}
    </AuthLayout>
  );
}
