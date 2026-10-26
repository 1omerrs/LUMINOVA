import { Icon } from "./Icon.tsx";

export function Pagination({
  page,
  pageSize,
  total,
  noun,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  noun: string;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const first = total > 0 ? (page - 1) * pageSize + 1 : 0;
  const last = Math.min(page * pageSize, total);
  return (
    <div className="flex items-center justify-between gap-3 border-t border-mist/70 px-4 py-3 text-[13px] text-slate sm:px-5">
      <p aria-live="polite">
        {first}–{last} / {total} {noun}
      </p>
      <div className="flex items-center gap-1">
        <PageButton label="Önceki sayfa" icon="chevron-left" disabled={page <= 1} onClick={() => onPage(page - 1)} />
        <span className="px-2 tabular-nums">
          {page} / {pages}
        </span>
        <PageButton label="Sonraki sayfa" icon="chevron-right" disabled={page >= pages} onClick={() => onPage(page + 1)} />
      </div>
    </div>
  );
}

function PageButton({ label, icon, disabled, onClick }: { label: string; icon: "chevron-left" | "chevron-right"; disabled: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="grid h-8 w-8 place-items-center rounded-lg text-graphite ring-1 ring-inset ring-mist transition-colors hover:bg-cloud disabled:cursor-not-allowed disabled:opacity-40"
    >
      <Icon name={icon} className="h-4 w-4" />
    </button>
  );
}
