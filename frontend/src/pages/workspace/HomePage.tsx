import { useEffect, useState } from "react";
import { Link } from "react-router";
import { Spinner } from "../../components/forms/Controls.tsx";
import { Icon } from "../../components/ui/Icon.tsx";
import { fetchActivity, type ActivityItem } from "../../lib/activity.ts";
import { fetchCustomers } from "../../lib/customers.ts";
import { fetchInsights, type Insight, type InsightList } from "../../lib/insights.ts";
import { fetchInventorySummary, type InventorySummary } from "../../lib/inventory.ts";
import { fetchSalesSummary, type SalesSummary } from "../../lib/sales.ts";
import { dueText, fetchTaskSummary, fetchToday, moveTask, type TaskSummary, type TodayView } from "../../lib/tasks.ts";
import { fetchProjectSummary, type ProjectSummary } from "../../lib/projects.ts";
import { fetchFinanceSummary, type FinanceSummary } from "../../lib/finance.ts";
import { formatMoney } from "../../lib/sales.ts";
import { fetchProductionSummary, type ProductionSummary } from "../../lib/production.ts";
import { timeAgo } from "../../lib/notifications.ts";
import { useWorkspace } from "../../lib/workspace.ts";

const today = new Intl.DateTimeFormat("tr-TR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

export function HomePage() {
  const { user, modules } = useWorkspace();
  const [date] = useState(() => today.format(new Date()));
  const [hour] = useState(() => new Date().getHours());
  const [activity, setActivity] = useState<ActivityItem[] | null>(null);
  const [insights, setInsights] = useState<InsightList | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchInsights()
      .then((next) => {
        if (!cancelled) setInsights(next);
      })
      .catch(() => {
        if (!cancelled) setInsights({ items: [], autopilot: false });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchActivity({ limit: 5 })
      .then((page) => {
        if (!cancelled) setActivity(page.items);
      })
      .catch(() => {
        if (!cancelled) setActivity([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const enabled = modules.filter((module) => module.enabled);
  const customersOn = enabled.some((module) => module.key === "customers");
  const inventoryOn = enabled.some((module) => module.key === "inventory");
  const [customerTotal, setCustomerTotal] = useState<number | null>(null);
  const [stock, setStock] = useState<InventorySummary | null>(null);
  const salesOn = enabled.some((module) => module.key === "sales");
  const [orders, setOrders] = useState<SalesSummary | null>(null);
  const tasksOn = enabled.some((module) => module.key === "tasks");
  const [tasks, setTasks] = useState<TaskSummary | null>(null);
  const productionOn = enabled.some((module) => module.key === "production");
  const [production, setProduction] = useState<ProductionSummary | null>(null);

  useEffect(() => {
    if (!productionOn) return;
    let cancelled = false;
    fetchProductionSummary()
      .then((summary) => {
        if (!cancelled) setProduction(summary);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [productionOn]);
  const financeOn = enabled.some((module) => module.key === "finance");
  const [finance, setFinance] = useState<FinanceSummary | null>(null);

  useEffect(() => {
    if (!financeOn) return;
    let cancelled = false;
    fetchFinanceSummary()
      .then((summary) => {
        if (!cancelled) setFinance(summary);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [financeOn]);
  const projectsOn = enabled.some((module) => module.key === "projects");
  const [projects, setProjects] = useState<ProjectSummary | null>(null);

  useEffect(() => {
    if (!projectsOn) return;
    let cancelled = false;
    fetchProjectSummary()
      .then((summary) => {
        if (!cancelled) setProjects(summary);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [projectsOn]);

  useEffect(() => {
    if (!tasksOn) return;
    let cancelled = false;
    fetchTaskSummary()
      .then((summary) => {
        if (!cancelled) setTasks(summary);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [tasksOn]);

  useEffect(() => {
    if (!salesOn) return;
    let cancelled = false;
    fetchSalesSummary()
      .then((summary) => {
        if (!cancelled) setOrders(summary);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [salesOn]);

  useEffect(() => {
    if (!customersOn) return;
    let cancelled = false;
    fetchCustomers({ pageSize: 1 })
      .then((page) => {
        if (!cancelled) setCustomerTotal(page.total);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [customersOn]);

  useEffect(() => {
    if (!inventoryOn) return;
    let cancelled = false;
    fetchInventorySummary()
      .then((summary) => {
        if (!cancelled) setStock(summary);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [inventoryOn]);

  const recordModules = customersOn || inventoryOn || tasksOn;
  const taskTotal = tasks ? tasks.todo + tasks.in_progress + tasks.done : 0;
  const orderTotal = orders ? orders.draft + orders.confirmed + orders.fulfilled + orders.cancelled : 0;
  const hasRecord = (customerTotal ?? 0) > 0 || (stock?.products ?? 0) > 0 || taskTotal > 0 || orderTotal > 0;
  const firstRecord = recordModules
    ? {
        label: "İlk kaydınızı ekleyin",
        done: hasRecord,
        note: hasRecord ? undefined : "Müşteri, stok veya görev modülünden başlayabilirsiniz.",
      }
    : {
        label: "İlk kaydınızı ekleyin",
        done: false,
        note: "Kayıt ekranları şu an Müşteri ve Teklifler, Stok ve Depo, Satış ve Siparişler ile Görev ve İş Yönetimi modüllerinde açık.",
      };
  const checklist: { label: string; done: boolean; note?: string }[] = [
    { label: "Hesabınız oluşturuldu", done: true },
    { label: "E-posta adresiniz doğrulandı", done: true },
    { label: `${enabled.length} modül ile çalışma alanınız kuruldu`, done: true },
    firstRecord,
  ];

  const financeMain = finance?.totals.find((row) => row.currency === "TRY") ?? null;
  const metrics: { label: string; value: string; note?: string; to: string; tone?: string }[] = [];
  if (orders) metrics.push({ label: "Açık sipariş", value: String(orders.draft + orders.confirmed), note: `${orders.confirmed} teslim bekliyor`, to: "/panel/satis" });
  if (financeMain) {
    metrics.push({ label: "Bu ay net", value: formatMoney(financeMain.net, "TRY"), tone: Number(financeMain.net) < 0 ? "text-error-text" : undefined, to: "/panel/finans" });
    metrics.push({
      label: "Açık alacak",
      value: formatMoney(financeMain.receivable, "TRY"),
      note: finance && finance.overdue_receivables > 0 ? `${finance.overdue_receivables} kaydın vadesi geçti` : undefined,
      to: "/panel/finans",
    });
  }
  if (stock) metrics.push({ label: "Kritik stok", value: String(stock.low), note: `${stock.products} ürün`, tone: stock.low > 0 ? "text-warning-text" : undefined, to: "/panel/stok?kritik=1" });
  if (tasks) metrics.push({ label: "Açık görev", value: String(tasks.todo + tasks.in_progress), note: tasks.overdue > 0 ? `${tasks.overdue} gecikmiş` : undefined, tone: tasks.overdue > 0 ? "text-error-text" : undefined, to: "/panel/gorevler" });
  if (projects) metrics.push({ label: "Aktif proje", value: String(projects.active), note: projects.overdue > 0 ? `${projects.overdue} gecikmiş` : undefined, to: "/panel/projeler" });
  if (production) metrics.push({ label: "Açık iş emri", value: String(production.planned + production.in_progress), to: "/panel/uretim" });
  if (customerTotal !== null) metrics.push({ label: "Müşteri", value: String(customerTotal), to: "/panel/musteriler" });

  const greeting = hour < 12 ? "Günaydın" : hour < 18 ? "İyi günler" : "İyi akşamlar";
  const urgent = insights?.items.filter((item) => item.severity !== "low").length ?? 0;
  const withTasks = insights?.items.filter((item) => item.task_id).length ?? 0;
  const status = !insights
    ? `${user.company_name} için bugünün özeti hazırlanıyor.`
    : insights.items.length === 0
      ? "Şu an ilgilenmeniz gereken bir konu yok. Kayıtlarınız düzenli kontrol ediliyor."
      : `${insights.items.length} konu ilginizi bekliyor${urgent ? `, ${urgent} tanesi öncelikli` : ""}.${withTasks ? ` ${withTasks} konu için görev açıldı ve sorumlusuna atandı.` : ""}`;

  return (
    <div className="space-y-10">
      <section>
        <p className="text-[13px] capitalize text-slate">{date}</p>
        <h1 className="mt-1.5 font-display text-[28px] font-semibold tracking-tight sm:text-[34px]">
          {greeting}, {user.first_name}.
        </h1>
        <p className="mt-2 max-w-2xl text-[15px] leading-7 text-slate">{status}</p>
      </section>

      <div className="grid grid-cols-1 gap-8 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-8">
          <Highlights insights={insights} />
          {tasksOn && insights ? <NextUp /> : null}
        </div>

        <aside className="space-y-8">
          {metrics.length > 0 && hasRecord ? (
            <section aria-labelledby="pulse-title">
              <div className="mb-2 flex items-end justify-between gap-3">
                <h2 id="pulse-title" className="text-[12px] font-semibold uppercase tracking-[0.08em] text-slate">
                  Göstergeler
                </h2>
                {enabled.some((module) => module.key === "reporting") ? (
                  <Link to="/panel/raporlar" className="text-[13px] font-medium text-violet hover:underline">
                    Raporlar
                  </Link>
                ) : null}
              </div>
              <ul className="divide-y divide-hairline border-y border-hairline">
                {metrics.slice(0, 7).map((metric) => (
                  <li key={metric.label}>
                    <Link to={metric.to} className="flex items-baseline justify-between gap-3 py-2.5 hover:text-violet">
                      <span className="text-[13px] text-slate">{metric.label}</span>
                      <span className="text-right">
                        <span className={`block text-[15px] font-semibold tabular-nums ${metric.tone ?? "text-graphite"}`}>{metric.value}</span>
                        {metric.note ? <span className="block text-[11.5px] text-slate">{metric.note}</span> : null}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          {hasRecord ? null : <Checklist items={checklist} />}
          <RecentActivity activity={activity} />
        </aside>
      </div>
    </div>
  );
}

const severityDot: Record<Insight["severity"], string> = { high: "bg-error", medium: "bg-warning", low: "bg-slate/50" };
const SHOWN = 8;

function Highlights({ insights }: { insights: InsightList | null }) {
  const [expanded, setExpanded] = useState(false);
  if (!insights) {
    return (
      <p role="status" className="flex items-center gap-2.5 text-[14px] text-slate">
        <Spinner className="h-4 w-4 text-violet" /> Kayıtlarınız kontrol ediliyor.
      </p>
    );
  }
  const items = expanded ? insights.items : insights.items.slice(0, SHOWN);
  return (
    <section aria-labelledby="highlights-title">
      <div className="mb-2 flex items-end justify-between gap-3">
        <h2 id="highlights-title" className="text-[12px] font-semibold uppercase tracking-[0.08em] text-slate">
          Öne çıkanlar
        </h2>
        <span className="text-[12px] text-slate">{insights.autopilot ? "Otomatik görevler açık" : "Otomatik görevler kapalı"}</span>
      </div>
      {insights.items.length === 0 ? (
        <div className="rounded-2xl border border-mist/80 bg-surface px-5 py-8 text-[14px] leading-6 text-slate">
          <p className="font-semibold text-graphite">Her şey yolunda.</p>
          Vadesi geçen tahsilat, kritik stok, cevapsız teklif, bekleyen teslimat veya kayan proje çıktığında burada nedeniyle birlikte görünür.
        </div>
      ) : (
        <ul className="divide-y divide-hairline overflow-hidden rounded-2xl border border-mist/80 bg-surface">
          {items.map((item) => (
            <li key={item.key} className="flex flex-col gap-2 px-5 py-3.5 sm:flex-row sm:items-center sm:gap-4">
              <span aria-hidden className={`hidden h-2 w-2 shrink-0 rounded-full sm:block ${severityDot[item.severity]}`} />
              <div className="min-w-0 flex-1">
                <p className="text-[14px] font-semibold leading-5">{item.title}</p>
                <p className="mt-0.5 text-[12.5px] leading-5 text-slate">{item.detail}</p>
              </div>
              <div className="flex shrink-0 items-center gap-3 text-[13px]">
                {item.task_id ? (
                  <Link to={`/panel/gorevler?gorev=${item.task_id}`} className="rounded-full bg-violet/10 px-2.5 py-1 text-[12px] font-semibold text-violet hover:bg-violet/15">
                    Görev{item.task_assignee ? ` · ${item.task_assignee.split(" ")[0]}` : " açıldı"}
                  </Link>
                ) : null}
                <Link to={item.link} className="font-semibold text-graphite hover:text-violet">
                  Aç
                </Link>
              </div>
            </li>
          ))}
          {insights.items.length > SHOWN ? (
            <li>
              <button type="button" onClick={() => setExpanded((value) => !value)} className="w-full px-5 py-2.5 text-left text-[13px] font-semibold text-violet hover:bg-cloud/50">
                {expanded ? "Daha az göster" : `${insights.items.length - SHOWN} konu daha`}
              </button>
            </li>
          ) : null}
        </ul>
      )}
    </section>
  );
}

function NextUp() {
  const [view, setView] = useState<TodayView | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchToday()
      .then((next) => {
        if (!cancelled) setView(next);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [version]);

  if (!view) return null;
  const queue = [...view.overdue, ...view.due_today, ...view.in_progress, ...view.unblocked, ...view.upcoming].slice(0, 6);
  return (
    <section aria-labelledby="next-title">
      <div className="mb-2 flex items-end justify-between gap-3">
        <h2 id="next-title" className="text-[12px] font-semibold uppercase tracking-[0.08em] text-slate">
          Sıradaki işlerim
        </h2>
        <Link to="/panel/gorevler" className="text-[13px] font-medium text-violet hover:underline">
          Günüm
        </Link>
      </div>
      {queue.length === 0 ? (
        <p className="rounded-2xl border border-mist/80 bg-surface px-5 py-6 text-[14px] text-slate">Size atanmış açık iş yok.</p>
      ) : (
        <ul className="divide-y divide-hairline overflow-hidden rounded-2xl border border-mist/80 bg-surface">
          {queue.map((task) => {
            const due = dueText(task, view.today);
            return (
              <li key={task.id} className="flex items-center gap-3 px-5 py-3">
                <button
                  type="button"
                  role="checkbox"
                  aria-checked={false}
                  disabled={task.blocked}
                  aria-label={`“${task.title}” görevini tamamla`}
                  onClick={() => void moveTask(task.id, "done").then(() => setVersion((value) => value + 1), () => undefined)}
                  className="grid h-[18px] w-[18px] shrink-0 place-items-center rounded-full border border-stone text-transparent transition-colors hover:border-success hover:text-success disabled:opacity-40"
                >
                  <Icon name="check" className="h-3 w-3" strokeWidth={2.6} />
                </button>
                <Link to={`/panel/gorevler?gorev=${task.id}`} className="min-w-0 flex-1">
                  <span className="block truncate text-[14px] font-medium hover:underline">{task.title}</span>
                  <span className="block truncate text-[12px] text-slate">
                    {[task.automatic ? "Otomatik" : null, task.customer_name, task.order_code, task.project_name].filter(Boolean).join(" · ")}
                  </span>
                </Link>
                {due ? <span className={`shrink-0 text-[12px] ${due.tone === "late" ? "font-semibold text-error-text" : "text-slate"}`}>{due.text}</span> : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function Checklist({ items }: { items: { label: string; done: boolean; note?: string }[] }) {
  return (
    <section aria-labelledby="setup-title">
      <h2 id="setup-title" className="mb-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-slate">
        Başlangıç adımları
      </h2>
      <ol className="space-y-3">
        {items.map((item) => (
          <li key={item.label} className="flex gap-3">
            <span className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full ${item.done ? "bg-success/12 text-success-text" : "border border-dashed border-stone"}`}>
              {item.done ? <Icon name="check" className="h-3 w-3" strokeWidth={2.4} /> : null}
            </span>
            <span>
              <span className={`block text-[14px] ${item.done ? "text-graphite" : "font-medium"}`}>{item.label}</span>
              {item.note ? <span className="mt-0.5 block text-[12px] leading-5 text-slate">{item.note}</span> : null}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function RecentActivity({ activity }: { activity: ActivityItem[] | null }) {
  return (
    <section aria-labelledby="activity-title">
      <div className="mb-3 flex items-end justify-between gap-3">
        <h2 id="activity-title" className="text-[12px] font-semibold uppercase tracking-[0.08em] text-slate">
          Son etkinlikler
        </h2>
        {activity && activity.length > 0 ? (
          <Link to="/panel/aktiviteler" className="text-[13px] font-medium text-violet hover:underline">
            Tümünü gör
          </Link>
        ) : null}
      </div>
      {activity === null ? null : activity.length === 0 ? (
        <p className="text-[13px] text-slate">Henüz etkinlik yok.</p>
      ) : (
        <ul className="space-y-4 border-l border-mist pl-4">
          {activity.map((item) => (
            <li key={item.id} className="relative">
              <span aria-hidden className="absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-cloud bg-violet" />
              <p className="text-[14px] leading-5">
                <span className="font-medium">{item.actor_name}</span> {item.verb}
                {item.target ? <span className="font-medium"> {item.target}</span> : null}
              </p>
              {item.detail ? <p className="mt-0.5 text-[13px] leading-5 text-slate">{item.detail}</p> : null}
              <time dateTime={item.created_at} className="mt-1 block text-[12px] text-slate/80">
                {timeAgo(item.created_at)}
              </time>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

