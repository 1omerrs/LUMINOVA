import { useId, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from "react";
import { Icon } from "../ui/Icon.tsx";

const inputBase =
  "h-10 w-full rounded-lg border bg-surface px-3 text-[14px] text-graphite outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-slate/55 focus:border-violet focus:shadow-[0_0_0_3px_rgba(91,71,214,0.14)]";

type FieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "onChange" | "value"> & {
  label: string;
  value: string;
  onValue: (value: string) => void;
  error?: string;
  hint?: ReactNode;
  trailing?: ReactNode;
  labelAction?: ReactNode;
};

export function Field({ label, value, onValue, error, hint, trailing, labelAction, id, className = "", ...input }: FieldProps) {
  const generated = useId();
  const fieldId = id ?? generated;
  const hintId = `${fieldId}-hint`;
  const errorId = `${fieldId}-error`;
  const describedBy = [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(" ") || undefined;

  return (
    <div className={className}>
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={fieldId} className="text-[13px] font-medium text-graphite">
          {label}
        </label>
        {labelAction}
      </div>
      <div className="relative mt-1.5">
        <input
          {...input}
          id={fieldId}
          value={value}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          onChange={(event) => onValue(event.target.value)}
          className={`${inputBase} ${trailing ? "pr-11" : ""} ${error ? "border-error/70 focus:border-error focus:shadow-[0_0_0_4px_rgba(220,38,38,0.12)]" : "border-mist hover:border-stone"}`}
        />
        {trailing ? <div className="absolute inset-y-0 right-1.5 flex items-center">{trailing}</div> : null}
      </div>
      {error ? (
        <p id={errorId} className="mt-1.5 flex items-start gap-1.5 text-[13px] leading-5 text-error-text">
          <Icon name="alert" className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={1.8} />
          {error}
        </p>
      ) : hint ? (
        <div id={hintId} className="mt-1.5 text-[13px] leading-5 text-slate">
          {hint}
        </div>
      ) : null}
    </div>
  );
}

export function TextArea({
  label,
  value,
  onValue,
  error,
  hint,
  maxLength,
  rows = 4,
  name,
}: {
  label: string;
  value: string;
  onValue: (value: string) => void;
  error?: string;
  hint?: ReactNode;
  maxLength?: number;
  rows?: number;
  name?: string;
}) {
  const fieldId = useId();
  const noteId = `${fieldId}-note`;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={fieldId} className="text-[13px] font-medium text-graphite">
          {label}
        </label>
        {maxLength ? (
          <span className={`text-[12px] tabular-nums ${value.length > maxLength ? "text-error-text" : "text-slate"}`} aria-hidden>
            {value.length} / {maxLength}
          </span>
        ) : null}
      </div>
      <textarea
        id={fieldId}
        name={name}
        rows={rows}
        value={value}
        aria-invalid={error ? true : undefined}
        aria-describedby={error || hint ? noteId : undefined}
        onChange={(event) => onValue(event.target.value)}
        className={`${inputBase} mt-1.5 h-auto resize-y py-2.5 leading-6 ${error ? "border-error/70" : "border-mist hover:border-stone"}`}
      />
      {error ? (
        <p id={noteId} className="mt-1.5 flex items-start gap-1.5 text-[13px] leading-5 text-error-text">
          <Icon name="alert" className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={1.8} />
          {error}
        </p>
      ) : hint ? (
        <div id={noteId} className="mt-1.5 text-[13px] leading-5 text-slate">
          {hint}
        </div>
      ) : null}
    </div>
  );
}

export function PasswordField(props: Omit<FieldProps, "type" | "trailing">) {
  const [visible, setVisible] = useState(false);
  return (
    <Field
      {...props}
      type={visible ? "text" : "password"}
      trailing={
        <button
          type="button"
          onClick={() => setVisible((current) => !current)}
          aria-label={visible ? "Şifreyi gizle" : "Şifreyi göster"}
          aria-pressed={visible}
          className="grid h-8 w-8 place-items-center rounded-lg text-slate transition-colors hover:bg-cloud hover:text-graphite"
        >
          <Icon name={visible ? "eye-off" : "eye"} className="h-[18px] w-[18px]" />
        </button>
      }
    />
  );
}

export function Checkbox({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <label className="group inline-flex cursor-pointer select-none items-center gap-2.5 text-[13px] text-graphite">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="peer sr-only" />
      <span
        aria-hidden
        className="grid h-[18px] w-[18px] place-items-center rounded-[5px] border border-stone bg-surface text-white transition-colors peer-checked:border-violet peer-checked:bg-violet peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-violet group-hover:border-violet/60"
      >
        <Icon name="check" className={`h-3 w-3 transition-opacity ${checked ? "opacity-100" : "opacity-0"}`} strokeWidth={2.4} />
      </span>
      {label}
    </label>
  );
}

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={`animate-spin ${className}`}>
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2.5" />
      <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  pending?: boolean;
  pendingLabel?: string;
  variant?: "primary" | "accent" | "dark" | "quiet" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
};

const variants = {
  primary: "bg-midnight text-onink shadow-[0_1px_0_rgba(255,255,255,0.08)_inset] hover:bg-ink-soft active:bg-graphite",
  accent: "bg-violet text-white hover:bg-violet-deep",
  dark: "bg-graphite text-onink hover:bg-midnight",
  quiet: "bg-surface text-graphite ring-1 ring-inset ring-mist hover:bg-paper hover:ring-stone",
  ghost: "text-graphite hover:bg-midnight/[0.05]",
  danger: "bg-error text-white hover:bg-error-text",
};

const sizes = { sm: "h-8 px-3 text-[12.5px]", md: "h-9 px-3.5 text-[13px]", lg: "h-10 px-4 text-[14px]" };

export function Button({ pending = false, pendingLabel, variant = "primary", size = "md", className = "", children, disabled, ...button }: ButtonProps) {
  return (
    <button
      {...button}
      disabled={disabled || pending}
      aria-busy={pending || undefined}
      className={`inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-lg font-medium transition-[background-color,box-shadow,opacity] duration-150 disabled:cursor-not-allowed disabled:opacity-50 ${sizes[size]} ${variants[variant]} ${className}`}
    >
      {pending ? <Spinner /> : null}
      {pending && pendingLabel ? pendingLabel : children}
    </button>
  );
}

export function Alert({ tone, children }: { tone: "error" | "success" | "info"; children: ReactNode }) {
  const styles = {
    error: "border-error/25 bg-error/[0.05] text-error-text",
    success: "border-success/25 bg-success/[0.06] text-success-text",
    info: "border-mist bg-paper text-graphite",
  };
  const icon = tone === "error" ? "alert" : tone === "success" ? "check" : "info";
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`flex items-start gap-2.5 rounded-lg border px-3.5 py-2.5 text-[13px] leading-5 ${styles[tone]}`}>
      <Icon name={icon} className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={1.8} />
      <div className="min-w-0">{children}</div>
    </div>
  );
}
