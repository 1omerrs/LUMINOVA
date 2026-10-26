import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router";
import { fetchCustomerDetail, type Customer, type CustomerOverview, type Money, type OverviewLink } from "../../lib/customers.ts";
import { ApiRequestError } from "../../lib/http.ts";
import { createLink } from "../../lib/intent.ts";
import { timeAgo } from "../../lib/notifications.ts";
import { formatDate, formatMoney, type Currency } from "../../lib/sales.ts";
import { createTask } from "../../lib/tasks.ts";
import { useWorkspace } from "../../lib/workspace.ts";
import { Alert, Button, Spinner } from "../forms/Controls.tsx";
import { Icon } from "../ui/Icon.tsx";
import { Sheet } from "../ui/Sheet.tsx";

type Detail = { customer: Customer; overview: CustomerOverview };

const tone: Record<string, string> = {
  draft: "text-slate",
  confirmed: "text-violet",
  sent: "text-violet",
  fulfilled: "text-success-text",
  accepted: "text-success-text",
  completed: "text-success-text",
  active: "text-violet",
  cancelled: "text-slate line-through",
  rejected: "text-error-text",
  overdue: "text-error-text",
  pending: "text-warning-text",
};

function money(list: Money[]): string {
  if (list.length === 0) return "—";
  return list.map((item) => formatMoney(item.amount, item.currency as Currency)).join(" · ");
}

export function CustomerDetail({ customerId, onClose, onEdit }: { customerId: string; onClose: () => void; onEdit: (customer: Customer) => void }) {
  const { modules } = useWorkspace();
  const on = (key: string) => modules.some((module) => module.key === key && module.enabled);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    fetchCustomerDetail(customerId)
      .then((next) => {
        if (!cancelled) setDetail(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiRequestError ? caught.message : "Müşteri yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [customerId, version]);

  const customer = detail?.customer;
  const overview = detail?.overview;
  const intent = customer ? { id: customer.id, label: customer.name } : null;

  return (
    <Sheet wide title={customer?.name ?? "Müşteri"} description={customer ? [customer.email, customer.phone].filter(Boolean).join(" · ") || "İletişim bilgisi yok" : undefined} onClose={onClose}>
      {error ? <Alert tone="error">{error}</Alert> : null}
      {!detail && !error ? (
        <p className="flex items-center gap-2 text-[14px] text-slate">
          <Spinner /> Müşteri yükleniyor
        </p>
      ) : null}
      {customer && overview && intent ? (
        <div className="space-y-8">
          <div className="flex flex-wrap gap-2">
            {on("customers") ? (
              <ActionLink to={createLink("/panel/musteriler?bolum=teklifler", intent)} icon="plus">
                Teklif hazırla
              </ActionLink>
            ) : null}
            {on("sales") ? (
              <ActionLink to={createLink("/panel/satis", intent)} icon="plus">
                Sipariş oluştur
              </ActionLink>
            ) : null}
            {on("projects") ? (
              <ActionLink to={createLink("/panel/projeler", intent)} icon="plus">
                Proje aç
              </ActionLink>
            ) : null}
            <Button variant="ghost" size="sm" onClick={() => onEdit(customer)}>
              <Icon name="pencil" className="h-3.5 w-3.5" /> Bilgileri düzenle
            </Button>
          </div>

          <dl className="grid grid-cols-2 divide-hairline border-y border-hairline sm:grid-cols-4 sm:divide-x">
            <Figure label="Ciro" value={on("sales") ? money(overview.revenue) : "—"} note="Onaylı ve teslim edilen siparişler" />
            <Figure label="Açık sipariş" value={on("sales") ? String(overview.open_orders) : "—"} note={on("sales") ? `Toplam ${overview.order_count} sipariş` : undefined} />
            <Figure label="Açık teklif" value={on("customers") ? String(overview.open_quotes) : "—"} />
            <Figure
              label="Bekleyen tahsilat"
              value={overview.finance ? money(overview.finance.receivable) : "—"}
              note={overview.finance && overview.finance.overdue > 0 ? `${overview.finance.overdue} kaydın vadesi geçti` : undefined}
              alert={Boolean(overview.finance && overview.finance.overdue > 0)}
            />
          </dl>

          {customer.note ? <p className="whitespace-pre-line border-l-2 border-mist pl-3 text-[13px] leading-6 text-ink-soft">{customer.note}</p> : null}

          <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_260px]">
            <div className="min-w-0 space-y-8">
              {on("sales") ? <Records title="Siparişler" empty="Bu müşteriye ait sipariş yok." rows={overview.orders} link="/panel/satis" /> : null}
              {on("customers") ? <Records title="Teklifler" empty="Bu müşteriye ait teklif yok." rows={overview.quotes} link="/panel/musteriler?bolum=teklifler" /> : null}
              {on("projects") ? <Records title="Projeler" empty="Bu müşteriye bağlı proje yok." rows={overview.projects} link="/panel/projeler" plain /> : null}
              {overview.finance ? <Records title="Bekleyen tahsilatlar" empty="Bekleyen tahsilat yok." rows={overview.finance.pending} link="/panel/finans" /> : null}
            </div>
            <aside className="space-y-8">
              {on("tasks") ? <Tasks customerId={customer.id} tasks={overview.open_tasks} onAdded={reload} /> : null}
              <section aria-labelledby="timeline-title">
                <h3 id="timeline-title" className="text-[12px] font-medium uppercase tracking-[0.08em] text-slate">
                  Geçmiş
                </h3>
                <ol className="mt-3 space-y-3 border-l border-mist pl-4">
                  {overview.timeline.map((item, index) => (
                    <li key={`${item.kind}-${index}`} className="relative">
                      <span aria-hidden className="absolute -left-[19.5px] top-1.5 h-1.5 w-1.5 rounded-full bg-ink-soft" />
                      <p className="text-[13px] leading-5">{item.link ? <Link to={item.link} className="hover:underline">{item.label}</Link> : item.label}</p>
                      <time dateTime={item.at} className="text-[11.5px] text-slate">
                        {timeAgo(item.at)}
                      </time>
                    </li>
                  ))}
                </ol>
              </section>
            </aside>
          </div>
        </div>
      ) : null}
    </Sheet>
  );
}

function ActionLink({ to, icon, children }: { to: string; icon: "plus"; children: ReactNode }) {
  return (
    <Link to={to} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-surface px-3 text-[12.5px] font-medium text-graphite ring-1 ring-inset ring-mist transition-colors hover:bg-paper hover:ring-stone">
      <Icon name={icon} className="h-3.5 w-3.5" /> {children}
    </Link>
  );
}

function Figure({ label, value, note, alert = false }: { label: string; value: string; note?: string; alert?: boolean }) {
  return (
    <div className="px-0 py-3.5 sm:px-4 sm:first:pl-0">
      <dt className="text-[11.5px] font-medium uppercase tracking-[0.06em] text-slate">{label}</dt>
      <dd className="mt-1 truncate text-[17px] font-semibold tabular-nums tracking-tight text-midnight">{value}</dd>
      {note ? <dd className={`mt-0.5 truncate text-[11.5px] ${alert ? "text-error-text" : "text-slate"}`}>{note}</dd> : null}
    </div>
  );
}

function Records({ title, empty, rows, link, plain = false }: { title: string; empty: string; rows: OverviewLink[]; link: string; plain?: boolean }) {
  return (
    <section>
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-[12px] font-medium uppercase tracking-[0.08em] text-slate">{title}</h3>
        <Link to={link} aria-label={`${title}: tümünü göster`} className="text-[12px] font-medium text-slate hover:text-graphite">
          Tümü →
        </Link>
      </div>
      {rows.length === 0 ? (
        <p className="mt-2 text-[13px] text-slate">{empty}</p>
      ) : (
        <table className="mt-2 w-full text-[13px]">
          <tbody className="divide-y divide-hairline">
            {rows.map((row) => (
              <tr key={row.id}>
                <td className={plain ? "w-1/2 max-w-0 truncate py-2 pr-3 font-medium" : "whitespace-nowrap py-2 pr-4 font-medium tabular-nums"}>{row.code}</td>
                <td className={`w-full whitespace-nowrap py-2 pr-3 text-[12px] ${tone[row.status] ?? "text-slate"}`}>{row.status_label}</td>
                <td className="whitespace-nowrap py-2 pr-3 text-[12px] text-slate">{row.when ? formatDate(row.when) : ""}</td>
                <td className="whitespace-nowrap py-2 text-right tabular-nums">{row.amount && row.currency ? formatMoney(row.amount, row.currency as Currency) : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function Tasks({ customerId, tasks, onAdded }: { customerId: string; tasks: CustomerOverview["open_tasks"]; onAdded: () => void }) {
  const [title, setTitle] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (title.trim().length < 2) {
      setError("Görev en az 2 karakter olmalı.");
      return;
    }
    setPending(true);
    setError("");
    try {
      await createTask({ title: title.trim(), description: "", status: "todo", priority: "normal", due_date: null, assignee_id: null, project_id: null, customer_id: customerId });
      setTitle("");
      onAdded();
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Görev eklenemedi.");
    } finally {
      setPending(false);
    }
  }

  return (
    <section aria-labelledby="customer-tasks">
      <div className="flex items-baseline justify-between gap-3">
        <h3 id="customer-tasks" className="text-[12px] font-medium uppercase tracking-[0.08em] text-slate">
          Açık görevler
        </h3>
        <Link to={`/panel/gorevler?musteri=${customerId}`} className="text-[12px] font-medium text-slate hover:text-graphite">
          Tümü →
        </Link>
      </div>
      <form onSubmit={(event) => void onSubmit(event)} className="mt-2 flex gap-1.5">
        <label className="min-w-0 flex-1">
          <span className="sr-only">Bu müşteri için görev</span>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            readOnly={pending}
            placeholder="Görev ekle…"
            maxLength={200}
            className="h-8 w-full rounded-md border border-mist bg-surface px-2.5 text-[13px] outline-none focus:border-violet"
          />
        </label>
        <Button type="submit" size="sm" variant="quiet" pending={pending}>
          Ekle
        </Button>
      </form>
      {error ? <p className="mt-1.5 text-[12px] text-error-text">{error}</p> : null}
      {tasks.length === 0 ? (
        <p className="mt-2 text-[13px] text-slate">Açık görev yok.</p>
      ) : (
        <ul className="mt-2 space-y-1.5">
          {tasks.map((task) => (
            <li key={task.id} className="flex items-start gap-2 text-[13px] leading-5">
              <span aria-hidden className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${task.overdue ? "bg-error" : task.status === "in_progress" ? "bg-violet" : "bg-mist"}`} />
              <span className="min-w-0 flex-1">
                {task.title}
                {task.due_date ? <span className={`ml-1.5 text-[11.5px] ${task.overdue ? "text-error-text" : "text-slate"}`}>{formatDate(task.due_date)}</span> : null}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
