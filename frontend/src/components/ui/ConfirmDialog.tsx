import { useEffect, useRef, useState, type ReactNode } from "react";
import { ApiRequestError } from "../../lib/http.ts";
import { Alert, Button } from "../forms/Controls.tsx";
import { Icon } from "./Icon.tsx";

export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  pendingLabel,
  onConfirm,
  onClose,
}: {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  pendingLabel: string;
  onConfirm: () => Promise<void>;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);

  async function confirm() {
    setPending(true);
    setError("");
    try {
      await onConfirm();
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "İşlem tamamlanamadı.");
      setPending(false);
    }
  }

  return (
    <dialog
      ref={dialog}
      aria-labelledby="confirm-title"
      onCancel={(event) => {
        event.preventDefault();
        if (!pending) onClose();
      }}
      className="m-auto w-[min(420px,calc(100vw-32px))] rounded-2xl border border-mist/80 bg-surface p-0 text-graphite shadow-[0_32px_64px_-24px_rgba(32,36,50,0.45)] backdrop:bg-rail/50"
    >
      <div className="p-6">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-error/[0.08] text-error-text">
          <Icon name="trash" />
        </span>
        <h2 id="confirm-title" className="mt-4 text-[17px] font-semibold">
          {title}
        </h2>
        <div className="mt-2 text-[14px] leading-6 text-slate">{children}</div>
        {error ? (
          <div className="mt-4">
            <Alert tone="error">{error}</Alert>
          </div>
        ) : null}
      </div>
      <div className="flex justify-end gap-2 border-t border-mist/70 bg-cloud/60 px-6 py-4">
        <Button variant="quiet" autoFocus onClick={onClose} disabled={pending}>
          Vazgeç
        </Button>
        <Button variant="danger" onClick={() => void confirm()} pending={pending} pendingLabel={pendingLabel}>
          {confirmLabel}
        </Button>
      </div>
    </dialog>
  );
}
