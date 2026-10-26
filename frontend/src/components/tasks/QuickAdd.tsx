import { useState, type FormEvent } from "react";
import { ApiRequestError } from "../../lib/http.ts";
import { createTask, type Task } from "../../lib/tasks.ts";
import { Spinner } from "../forms/Controls.tsx";
import { Icon } from "../ui/Icon.tsx";

export function QuickAdd({
  assigneeId,
  projectId = null,
  className = "px-3 pb-1 pt-1",
  onCreated,
}: {
  assigneeId: string | null;
  projectId?: string | null;
  className?: string;
  onCreated: (task: Task) => void;
}) {
  const [title, setTitle] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    if (title.trim().length < 2) {
      setError("Başlık en az 2 karakter olmalı.");
      return;
    }
    setPending(true);
    setError("");
    try {
      const task = await createTask({
        title,
        description: "",
        status: "todo",
        priority: "normal",
        due_date: null,
        assignee_id: assigneeId,
        project_id: projectId,
      });
      setTitle("");
      onCreated(task);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Görev eklenemedi.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate className={className}>
      <div className="flex items-center gap-2 rounded-xl border border-dashed border-mist bg-surface px-3 transition-colors focus-within:border-violet focus-within:border-solid focus-within:shadow-[0_0_0_4px_rgba(91,71,214,0.12)]">
        <Icon name="plus" className="h-4 w-4 shrink-0 text-slate" strokeWidth={2} />
        <input
          aria-label="Hızlı görev ekle"
          aria-invalid={error ? true : undefined}
          value={title}
          maxLength={200}
          readOnly={pending}
          onChange={(event) => {
            setTitle(event.target.value);
            setError("");
          }}
          onKeyDown={(event) => {
            if (event.key !== "Enter" || event.nativeEvent.isComposing) return;
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
          }}
          placeholder="Görev ekle ve Enter'a bas"
          className="h-10 min-w-0 flex-1 bg-transparent text-[14px] outline-none placeholder:text-slate/70"
        />
        {pending ? <Spinner className="h-4 w-4 text-violet" /> : null}
      </div>
      {error ? <p className="mt-1.5 px-1 text-[12px] text-error-text">{error}</p> : null}
    </form>
  );
}
