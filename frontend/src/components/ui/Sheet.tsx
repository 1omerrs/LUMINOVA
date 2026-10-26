import { useEffect, useRef, type FormEvent, type ReactNode } from "react";
import { Icon } from "./Icon.tsx";

export function Sheet({
  title,
  description,
  busy = false,
  onClose,
  onSubmit,
  initialFocus,
  footer,
  wide = false,
  children,
}: {
  wide?: boolean;
  title: string;
  description?: ReactNode;
  busy?: boolean;
  onClose: () => void;
  onSubmit?: (event: FormEvent<HTMLFormElement>) => void;
  initialFocus?: string;
  footer?: ReactNode;
  children: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = `sheet-${title.replace(/\W+/g, "-")}`;

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    if (initialFocus) element?.querySelector<HTMLElement>(initialFocus)?.focus();
    return () => element?.close();
  }, [initialFocus]);

  const body = (
    <>
      <header className="flex items-start justify-between gap-4 border-b border-mist/70 px-6 py-5">
        <div className="min-w-0">
          <h2 id={titleId} className="text-[17px] font-semibold">
            {title}
          </h2>
          {description ? <div className="mt-0.5 text-[13px] text-slate">{description}</div> : null}
        </div>
        <button
          type="button"
          onClick={onClose}
          disabled={busy}
          aria-label="Paneli kapat"
          className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-slate transition-colors hover:bg-cloud hover:text-graphite"
        >
          <Icon name="close" className="h-[18px] w-[18px]" />
        </button>
      </header>
      <div className="flex-1 overflow-y-auto px-6 py-6">{children}</div>
      {footer ? <footer className="flex justify-end gap-2 border-t border-mist/70 bg-cloud/50 px-6 py-4">{footer}</footer> : null}
    </>
  );

  return (
    <dialog
      ref={dialog}
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
      className={`fixed inset-y-0 left-auto right-0 m-0 h-dvh max-h-none ${wide ? "w-[min(780px,100vw)]" : "w-[min(480px,100vw)]"} max-w-none animate-[sheet_200ms_ease-out] border-l border-mist/80 bg-surface p-0 text-graphite shadow-[-24px_0_48px_-24px_rgba(32,36,50,0.3)] backdrop:bg-rail/40`}
    >
      {onSubmit ? (
        <form noValidate onSubmit={onSubmit} className="flex h-full flex-col">
          {body}
        </form>
      ) : (
        <div className="flex h-full flex-col">{body}</div>
      )}
    </dialog>
  );
}
