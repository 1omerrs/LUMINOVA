import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { Alert, Button } from "../components/forms/Controls.tsx";
import { Icon } from "../components/ui/Icon.tsx";
import { PageStatus } from "../components/ui/PageStatus.tsx";
import { Wordmark } from "../components/ui/Wordmark.tsx";
import { ModuleIcon } from "../components/workspace/ModuleIcon.tsx";
import { fetchCurrentUser, logoutAccount, type CurrentUser } from "../lib/auth.ts";
import { ApiRequestError } from "../lib/http.ts";
import { completeSetup, fetchModules, requiredBy, withRequirements, type ModuleKey, type WorkspaceModule } from "../lib/modules.ts";

type Loaded = { user: CurrentUser; modules: WorkspaceModule[] };

export function SetupPage() {
  const navigate = useNavigate();
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [loadError, setLoadError] = useState("");
  const [chosen, setChosen] = useState<Set<ModuleKey>>(new Set());
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const user = await fetchCurrentUser();
      if (cancelled) return;
      if (user === null) {
        await navigate("/giris", { replace: true });
        return;
      }
      if (user.setup_completed) {
        await navigate("/panel", { replace: true });
        return;
      }
      const modules = await fetchModules();
      if (!cancelled) setLoaded({ user, modules });
    })().catch(() => {
      if (!cancelled) setLoadError("Kurulum bilgileri alınamadı.");
    });
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  const modules = useMemo(() => loaded?.modules ?? [], [loaded]);
  const effective = useMemo(() => withRequirements(modules, chosen), [modules, chosen]);

  if (!loaded) {
    return <PageStatus message={loadError || "Kurulum hazırlanıyor."} failed={Boolean(loadError)} />;
  }

  function toggle(key: ModuleKey) {
    setError("");
    setChosen((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function onCreate() {
    setPending(true);
    setError("");
    try {
      await completeSetup([...chosen]);
      await navigate("/panel", { replace: true });
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Çalışma alanı oluşturulamadı.");
      setPending(false);
    }
  }

  async function onLogout() {
    await logoutAccount();
    await navigate("/giris", { replace: true });
  }

  const count = effective.size;

  return (
    <div className="min-h-dvh bg-cloud text-graphite">
      <header className="border-b border-mist/70 bg-surface">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-5 sm:px-8">
          <Wordmark className="text-sm" />
          <div className="hidden items-center gap-3 sm:flex" aria-label="Kurulum adımı">
            <span className="text-[13px] text-slate">Adım 3 / 3</span>
            <span className="flex gap-1" aria-hidden>
              <span className="h-1 w-8 rounded-full bg-violet" />
              <span className="h-1 w-8 rounded-full bg-violet" />
              <span className="h-1 w-8 rounded-full bg-violet" />
            </span>
            <span className="text-[13px] font-medium">Modül seçimi</span>
          </div>
          <button type="button" onClick={() => void onLogout()} className="rounded-lg px-3 py-2 text-[13px] font-medium text-slate transition-colors hover:bg-cloud hover:text-graphite">
            Çıkış yap
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-5 pb-36 pt-10 sm:px-8 sm:pt-14">
        <p className="font-display text-[11px] font-semibold tracking-[0.18em] text-violet">{loaded.user.company_name.toLocaleUpperCase("tr")}</p>
        <h1 className="mt-3 max-w-2xl font-display text-[30px] font-semibold leading-[1.12] tracking-tight sm:text-[38px]">
          LUMINOVA çalışma alanınızı oluşturun.
        </h1>
        <p className="mt-4 max-w-2xl text-[15px] leading-7 text-slate">
          İşletmenizin ihtiyaç duyduğu modülleri seçin. Daha sonra profilinizden yeni modüller ekleyebilir veya mevcut seçimlerinizi değiştirebilirsiniz.
        </p>

        <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-3" role="group" aria-label="Modüller">
          {modules.map((module) => {
            const explicit = chosen.has(module.key);
            const auto = !explicit && effective.has(module.key);
            const reason = auto ? requiredBy(modules, chosen, module.key).map((item) => item.name).join(", ") : "";
            const checked = explicit || auto;
            return (
              <button
                key={module.key}
                type="button"
                role="checkbox"
                aria-checked={checked}
                aria-disabled={auto || undefined}
                aria-describedby={`setup-${module.key}`}
                onClick={() => (auto ? undefined : toggle(module.key))}
                className={`group relative flex min-h-[148px] flex-col rounded-2xl border bg-surface p-5 text-left transition-[border-color,box-shadow,transform,background-color] duration-200 ${
                  checked
                    ? "border-violet/70 bg-[#faf9f6] shadow-[0_0_0_4px_rgba(91,71,214,0.08)]"
                    : "border-mist/90 hover:-translate-y-px hover:border-stone hover:shadow-[0_10px_24px_-18px_rgba(32,36,50,0.4)]"
                } ${auto ? "cursor-default" : ""}`}
              >
                <span className="flex w-full items-start justify-between">
                  <span
                    className={`grid h-11 w-11 place-items-center rounded-xl transition-colors duration-200 ${
                      checked ? "bg-violet text-white" : "bg-cloud text-graphite ring-1 ring-inset ring-mist/80"
                    }`}
                  >
                    <ModuleIcon name={module.key} />
                  </span>
                  <span
                    aria-hidden
                    className={`grid h-5 w-5 place-items-center rounded-full border transition-all duration-200 ${
                      checked ? (auto ? "border-lavender bg-lavender text-white" : "border-violet bg-violet text-white") : "border-stone text-transparent group-hover:border-violet/60"
                    }`}
                  >
                    <Icon name="check" className={`h-3 w-3 transition-transform duration-200 ${checked ? "scale-100" : "scale-50"}`} strokeWidth={2.6} />
                  </span>
                </span>
                <span className="mt-4 text-[15px] font-semibold">{module.name}</span>
                <span id={`setup-${module.key}`} className="mt-1 text-[13px] leading-5 text-slate">
                  {auto ? <span className="font-medium text-violet">{reason} için gerekli olduğundan eklendi.</span> : module.summary}
                </span>
              </button>
            );
          })}
        </div>
      </main>

      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-mist/70 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <div className="min-w-0">
            {error ? (
              <Alert tone="error">{error}</Alert>
            ) : (
              <p className="text-[14px]" aria-live="polite">
                <span className="font-semibold">{count} modül seçildi</span>
                <span className="text-slate"> · {count === 0 ? "Devam etmek için en az bir modül seçin." : "Seçiminizi istediğiniz zaman değiştirebilirsiniz."}</span>
              </p>
            )}
          </div>
          <Button size="lg" onClick={() => void onCreate()} disabled={count === 0} pending={pending} pendingLabel="Çalışma alanınız hazırlanıyor" className="shrink-0">
            Çalışma alanımı oluştur
            <Icon name="arrow-right" className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
