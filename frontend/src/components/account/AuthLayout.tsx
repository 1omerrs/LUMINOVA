import type { ReactNode } from "react";
import { ModuleIcon } from "../workspace/ModuleIcon.tsx";
import { Icon } from "../ui/Icon.tsx";
import { Wordmark } from "../ui/Wordmark.tsx";
import type { ModuleKey } from "../../lib/modules.ts";

type Variant = "register" | "login";

const managerSteps = ["Hesabınızı oluşturun", "E-postanızı doğrulayın", "Modüllerinizi seçin"];
const memberSteps = ["Katılım koduyla kayıt olun", "E-postanızı doğrulayın", "Yöneticiniz onaylasın"];
const constellation: ModuleKey[] = ["sales", "inventory", "production", "customers", "finance", "tasks", "projects", "reporting", "automation"];

export function AuthLayout({
  variant,
  step = 1,
  eyebrow,
  title,
  description,
  children,
  footer,
  joining = false,
}: {
  variant: Variant;
  step?: 1 | 2 | 3;
  joining?: boolean;
  eyebrow?: string;
  title: string;
  description: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <main className="grid min-h-dvh bg-surface text-graphite lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <aside
        aria-hidden
        className={`relative hidden overflow-hidden bg-rail text-white lg:flex lg:flex-col ${variant === "login" ? "lg:order-2" : ""}`}
      >
        <div
          className="absolute inset-0 opacity-70"
          style={{
            backgroundImage:
              "linear-gradient(to right, rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.04) 1px, transparent 1px)",
            backgroundSize: "56px 56px",
            maskImage: "radial-gradient(ellipse at 30% 40%, black, transparent 75%)",
          }}
        />
        <div
          className={`absolute h-[520px] w-[520px] rounded-full bg-violet/25 blur-[120px] ${variant === "login" ? "-right-40 top-1/3" : "-left-40 -top-24"}`}
        />
        <div className="relative flex flex-1 flex-col px-12 py-10 xl:px-16">
          <Wordmark tone="light" className="text-sm" />
          {variant === "register" ? <RegisterAside step={step} steps={joining ? memberSteps : managerSteps} /> : <LoginAside />}
          <p className="text-xs text-white/45">Ödeme bilgisi istenmez. Verileriniz yalnızca kendi çalışma alanınızda görünür.</p>
        </div>
      </aside>

      <section className="flex min-h-dvh flex-col px-6 py-8 sm:px-10">
        <div className="lg:hidden">
          <Wordmark className="text-sm" />
        </div>
        <div className="mx-auto flex w-full max-w-[400px] flex-1 flex-col justify-center py-10">
          {eyebrow ? <p className="font-display text-[11px] font-semibold tracking-[0.18em] text-violet">{eyebrow}</p> : null}
          <h1 className="mt-3 font-display text-[28px] font-semibold leading-[1.15] tracking-tight sm:text-[32px]">{title}</h1>
          <p className="mt-3 text-[15px] leading-6 text-slate">{description}</p>
          <div className="mt-8">{children}</div>
          {footer ? <div className="mt-8 text-[14px] text-slate">{footer}</div> : null}
        </div>
      </section>
    </main>
  );
}

function RegisterAside({ step, steps }: { step: 1 | 2 | 3; steps: string[] }) {
  return (
    <div className="flex flex-1 flex-col justify-center py-16">
      <p className="max-w-md font-display text-[34px] font-semibold leading-[1.12] tracking-tight xl:text-[40px]">
        {steps === memberSteps ? "Üç adımda ekibinize katılın." : "Üç adımda kendi çalışma alanınız."}
      </p>
      <ol className="mt-12 max-w-sm space-y-1">
        {steps.map((label, index) => {
          const number = index + 1;
          const state = number < step ? "done" : number === step ? "current" : "next";
          return (
            <li key={label} className="relative flex items-center gap-4 py-3">
              {index < steps.length - 1 ? <span className="absolute left-[15px] top-[42px] h-[calc(100%-30px)] w-px bg-white/12" /> : null}
              <span
                className={`grid h-8 w-8 shrink-0 place-items-center rounded-full text-[13px] font-semibold ${
                  state === "current"
                    ? "bg-violet text-white shadow-[0_0_0_6px_rgba(91,71,214,0.18)]"
                    : state === "done"
                      ? "bg-white/12 text-lavender"
                      : "border border-white/15 text-white/45"
                }`}
              >
                {state === "done" ? <Icon name="check" className="h-4 w-4" strokeWidth={2} /> : number}
              </span>
              <span className={state === "next" ? "text-white/45" : "text-white"}>{label}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function LoginAside() {
  return (
    <div className="flex flex-1 flex-col justify-center py-16">
      <div className="grid w-fit grid-cols-3 gap-3">
        {constellation.map((key, index) => (
          <span
            key={key}
            className={`grid h-14 w-14 place-items-center rounded-2xl border ${
              index === 4 ? "border-violet/60 bg-violet/15 text-lavender" : "border-white/10 bg-white/[0.03] text-white/55"
            }`}
          >
            <ModuleIcon name={key} className="h-[22px] w-[22px]" />
          </span>
        ))}
      </div>
      <p className="mt-12 max-w-md font-display text-[34px] font-semibold leading-[1.12] tracking-tight xl:text-[40px]">
        Çalışma alanınız kaldığınız yerde.
      </p>
      <p className="mt-4 max-w-sm leading-7 text-white/60">Seçtiğiniz modüller ve tercihleriniz hesabınızla birlikte saklanır.</p>
    </div>
  );
}
