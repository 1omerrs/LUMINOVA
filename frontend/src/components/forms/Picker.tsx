import { useEffect, useId, useRef, useState } from "react";
import { Icon } from "../ui/Icon.tsx";
import { Spinner } from "./Controls.tsx";

export type PickerOption = { id: string; label: string; meta?: string };

export function Picker({
  label,
  value,
  onChange,
  search,
  placeholder,
  error,
  name,
  emptyText = "Sonuç yok.",
  compact = false,
  create,
}: {
  label: string;
  value: PickerOption | null;
  onChange: (option: PickerOption | null) => void;
  search: (query: string) => Promise<PickerOption[]>;
  placeholder: string;
  error?: string;
  name?: string;
  emptyText?: string;
  compact?: boolean;
  create?: { label: (term: string) => string; run: (term: string) => Promise<PickerOption> };
}) {
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<{ query: string; options: PickerOption[] } | null>(null);
  const [active, setActive] = useState(0);
  const term = query.trim();
  const options = results?.options ?? [];
  const loading = results?.query !== term;
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const canCreate =
    Boolean(create) && !loading && term.length >= 2 && !options.some((option) => option.label.toLocaleLowerCase("tr") === term.toLocaleLowerCase("tr"));
  const count = options.length + (canCreate ? 1 : 0);

  async function createNew() {
    if (!create || creating) return;
    setCreating(true);
    setCreateError("");
    try {
      choose(await create.run(term));
    } catch (caught) {
      setCreateError(caught instanceof Error ? caught.message : "Kayıt oluşturulamadı.");
    } finally {
      setCreating(false);
    }
  }

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      search(term)
        .then((found) => {
          if (cancelled) return;
          setResults({ query: term, options: found });
          setActive(0);
        })
        .catch(() => {
          if (!cancelled) setResults({ query: term, options: [] });
        });
    }, 200);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, term, search]);

  useEffect(() => {
    if (!open) return;
    function onPointer(event: PointerEvent) {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  function choose(option: PickerOption) {
    onChange(option);
    setOpen(false);
    setQuery("");
  }

  const listId = `${id}-list`;
  const errorId = `${id}-error`;
  const height = compact ? "h-10" : "h-11";

  return (
    <div ref={root} className="relative">
      <label htmlFor={id} className={compact ? "sr-only" : "text-[13px] font-medium text-graphite"}>
        {label}
      </label>
      {value ? (
        <div className={`${compact ? "" : "mt-1.5"} flex ${height} items-center justify-between gap-2 rounded-lg border border-mist bg-cloud/60 px-3`}>
          <span className="min-w-0">
            <span className="block truncate text-[14px] font-medium">{value.label}</span>
            {value.meta && !compact ? <span className="block truncate text-[12px] text-slate">{value.meta}</span> : null}
          </span>
          <button
            type="button"
            aria-label={`${label} seçimini kaldır`}
            onClick={() => {
              onChange(null);
              window.setTimeout(() => input.current?.focus(), 0);
            }}
            className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-slate hover:bg-surface hover:text-graphite"
          >
            <Icon name="close" className="h-4 w-4" />
          </button>
        </div>
      ) : (
        <div className={`relative ${compact ? "" : "mt-1.5"}`}>
          <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate" />
          <input
            ref={input}
            id={id}
            name={name}
            role="combobox"
            aria-expanded={open}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? errorId : undefined}
            aria-activedescendant={open && options[active] ? `${listId}-${active}` : undefined}
            autoComplete="off"
            value={query}
            placeholder={placeholder}
            onFocus={() => setOpen(true)}
            onClick={() => setOpen(true)}
            onChange={(event) => {
              setQuery(event.target.value);
              setOpen(true);
            }}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setOpen(true);
                setActive((current) => Math.min(current + 1, count - 1));
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setActive((current) => Math.max(current - 1, 0));
              } else if (event.key === "Enter" && open && options[active]) {
                event.preventDefault();
                choose(options[active]);
              } else if (event.key === "Enter" && open && canCreate && active === options.length) {
                event.preventDefault();
                void createNew();
              } else if (event.key === "Escape" && open) {
                event.preventDefault();
                event.stopPropagation();
                setOpen(false);
              }
            }}
            className={`${height} w-full rounded-lg border bg-surface pl-9 pr-3 text-[14px] outline-none transition-[border-color,box-shadow] placeholder:text-slate/70 focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)] ${
              error ? "border-error/70" : "border-mist hover:border-stone"
            }`}
          />
          {open ? (
            <ul
              id={listId}
              role="listbox"
              aria-label={label}
              className="absolute left-0 right-0 top-full z-20 mt-1 max-h-64 overflow-y-auto rounded-xl border border-mist/80 bg-surface p-1 shadow-[0_18px_40px_-18px_rgba(32,36,50,0.4)]"
            >
              {loading ? (
                <li className="flex items-center gap-2 px-3 py-2.5 text-[13px] text-slate">
                  <Spinner className="h-3.5 w-3.5 text-violet" /> Aranıyor
                </li>
              ) : options.length === 0 && !canCreate ? (
                <li className="px-3 py-2.5 text-[13px] text-slate">{emptyText}</li>
              ) : (
                options.map((option, index) => (
                  <li
                    key={option.id}
                    id={`${listId}-${index}`}
                    role="option"
                    aria-selected={index === active}
                    onPointerDown={(event) => event.preventDefault()}
                    onClick={() => choose(option)}
                    onPointerEnter={() => setActive(index)}
                    className={`cursor-pointer rounded-lg px-3 py-2 ${index === active ? "bg-cloud" : ""}`}
                  >
                    <span className="block truncate text-[14px] font-medium">{option.label}</span>
                    {option.meta ? <span className="block truncate text-[12px] text-slate">{option.meta}</span> : null}
                  </li>
                ))
              )}
              {canCreate && create ? (
                <li
                  id={`${listId}-${options.length}`}
                  role="option"
                  aria-selected={active === options.length}
                  onPointerDown={(event) => event.preventDefault()}
                  onClick={() => void createNew()}
                  onPointerEnter={() => setActive(options.length)}
                  className={`flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-[14px] font-semibold text-violet ${active === options.length ? "bg-cloud" : ""}`}
                >
                  {creating ? <Spinner className="h-3.5 w-3.5" /> : <Icon name="plus" className="h-4 w-4" strokeWidth={2} />}
                  <span className="truncate">{create.label(term)}</span>
                </li>
              ) : null}
            </ul>
          ) : null}
          {createError ? <p className="mt-1.5 text-[12.5px] text-error-text">{createError}</p> : null}
        </div>
      )}
      {error ? (
        <p id={errorId} className="mt-1.5 flex items-start gap-1.5 text-[13px] leading-5 text-error-text">
          <Icon name="alert" className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={1.8} />
          {error}
        </p>
      ) : null}
    </div>
  );
}
