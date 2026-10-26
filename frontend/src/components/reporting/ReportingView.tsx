import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { ApiRequestError } from "../../lib/http.ts";
import type { WorkspaceModule } from "../../lib/modules.ts";
import { fetchOverview, monthLabel, periods, type Period, type Ranked, type ReportOverview } from "../../lib/reports.ts";
import { formatMoney } from "../../lib/sales.ts";
import { Alert, Spinner } from "../forms/Controls.tsx";
import { BarChart } from "./BarChart.tsx";

const money = (value: number | string) => formatMoney(value, "TRY");
const count = (value: number) => new Intl.NumberFormat("tr-TR").format(value);
const VIOLET = "#5b47d6";
const LAVENDER = "#c4b5fd";
const GREEN = "#16a34a";
const RED = "#f87171";

type Load = { status: "loading" } | { status: "ready"; report: ReportOverview } | { status: "failed"; message: string };

export function ReportingView({ module }: { module: WorkspaceModule }) {
  const [period, setPeriod] = useState<Period>(6);
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchOverview(period)
      .then((report) => {
        if (!cancelled) setLoad({ status: "ready", report });
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoad({ status: "failed", message: error instanceof ApiRequestError ? error.message : "Rapor yüklenemedi." });
      });
    return () => {
      cancelled = true;
    };
  }, [period, reload]);

  const report = load.status === "ready" ? load.report : null;
  const range = report ? `${monthLabel(report.months[0], true)} – ${monthLabel(report.months[report.months.length - 1], true)}` : "";
  const sections = report ? [report.sales, report.finance, report.inventory, report.tasks, report.projects, report.production, report.customers].filter(Boolean) : [];

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-4">
          <div className="min-w-0">
            <h1 className="font-display text-[22px] font-semibold tracking-[-0.02em] text-midnight sm:text-[24px]">{module.name}</h1>
            <p className="mt-0.5 text-[14px] capitalize text-slate">{range || module.summary}</p>
          </div>
        </div>
        <div role="group" aria-label="Dönem" className="flex gap-1 rounded-xl bg-surface p-1 ring-1 ring-inset ring-mist">
          {periods.map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={period === value}
              onClick={() => setPeriod(value)}
              className={`h-9 rounded-[9px] px-3.5 text-[13px] font-semibold transition-colors ${period === value ? "bg-graphite text-onink" : "text-slate hover:text-graphite"}`}
            >
              Son {value} ay
            </button>
          ))}
        </div>
      </section>

      {load.status === "failed" ? (
        <Alert tone="error">
          {load.message}{" "}
          <button type="button" onClick={() => setReload((value) => value + 1)} className="font-semibold underline">
            Tekrar dene
          </button>
        </Alert>
      ) : !report ? (
        <p role="status" className="flex items-center gap-2.5 py-12 text-[14px] text-slate">
          <Spinner className="h-4 w-4 text-violet" /> Rapor hazırlanıyor.
        </p>
      ) : sections.length === 0 ? (
        <section className="rounded-2xl border border-mist/80 bg-surface px-6 py-14 text-center">
          <h2 className="text-[16px] font-semibold">Raporlanacak modül açık değil.</h2>
          <p className="mx-auto mt-2 max-w-md text-[14px] leading-6 text-slate">Satış, finans, stok veya görev modüllerini açtığınızda göstergeler burada gerçek kayıtlarınızdan hesaplanır.</p>
          <Link to="/panel/profil#moduller" className="mt-5 inline-block text-[14px] font-semibold text-violet hover:underline">
            Modül tercihlerine git
          </Link>
        </section>
      ) : (
        <>
          <section aria-label="Öne çıkan göstergeler" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {report.sales ? <Kpi label="Satış geliri" value={money(report.sales.total_revenue)} note={`${count(report.sales.order_count)} sipariş · ort. ${money(report.sales.average_order)}`} /> : null}
            {report.finance ? (
              <Kpi label="Net (gelir − gider)" value={money(report.finance.net)} tone={Number(report.finance.net) < 0 ? "text-error-text" : "text-graphite"} note={`Açık alacak ${money(report.finance.receivable)}`} />
            ) : null}
            {report.tasks ? <Kpi label="Görev tamamlama" value={`%${report.tasks.completion_rate}`} note={`${count(report.tasks.open)} açık · ${count(report.tasks.overdue)} gecikmiş`} /> : null}
            {report.inventory ? (
              <Kpi label="Kritik stok" value={count(report.inventory.low)} tone={report.inventory.low > 0 ? "text-warning-text" : "text-graphite"} note={`${count(report.inventory.products)} ürün takipte`} />
            ) : null}
            {report.projects ? <Kpi label="Aktif proje ilerlemesi" value={`%${report.projects.average_progress}`} note={`${count(report.projects.active)} aktif proje`} /> : null}
            {report.customers ? <Kpi label="Müşteri" value={count(report.customers.total)} note={`Dönemde ${count(sum(report.customers.new))} yeni`} /> : null}
            {report.production ? <Kpi label="Tamamlanan iş emri" value={count(sum(report.production.completed))} note={`${count(report.production.open)} açık iş emri`} /> : null}
          </section>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {report.sales ? (
              <Card title="Satış" link="/panel/satis">
                <BarChart title="Aylık satış geliri (TRY)" series={[{ label: "Gelir", color: VIOLET, points: report.sales.revenue }]} format={money} />
                {report.sales.other_currency_orders > 0 ? (
                  <p className="text-[12px] text-slate">{report.sales.other_currency_orders} siparişin para birimi TRY dışında; gelir toplamına katılmadı.</p>
                ) : null}
                <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                  <RankList title="En çok satış yapılan müşteriler" items={report.sales.top_customers} format={money} empty="Onaylanmış sipariş yok." />
                  <RankList title="En çok satılan ürünler" items={report.sales.top_products} empty="Stoklu ürün satışı yok." />
                </div>
              </Card>
            ) : null}

            {report.finance ? (
              <Card title="Finans" link="/panel/finans">
                <BarChart
                  title="Gelir ve gider (TRY)"
                  series={[
                    { label: "Gelir", color: GREEN, points: report.finance.income },
                    { label: "Gider", color: RED, points: report.finance.expense },
                  ]}
                  format={money}
                />
                <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                  <RankList title="Gider kategorileri" items={report.finance.expense_categories} format={money} empty="Bu dönemde gider yok." bars />
                  <dl className="space-y-2 text-[14px]">
                    <Row label="Toplam gelir" value={money(report.finance.total_income)} />
                    <Row label="Toplam gider" value={money(report.finance.total_expense)} />
                    <Row label="Açık alacak" value={money(report.finance.receivable)} note={report.finance.overdue_receivables ? `${report.finance.overdue_receivables} gecikmiş` : undefined} />
                    <Row label="Açık borç" value={money(report.finance.payable)} note={report.finance.overdue_payables ? `${report.finance.overdue_payables} gecikmiş` : undefined} />
                  </dl>
                </div>
              </Card>
            ) : null}

            {report.tasks ? (
              <Card title="Görevler" link="/panel/gorevler">
                <BarChart
                  title="Açılan ve tamamlanan görevler"
                  series={[
                    { label: "Açılan", color: LAVENDER, points: report.tasks.created },
                    { label: "Tamamlanan", color: VIOLET, points: report.tasks.completed },
                  ]}
                  format={count}
                />
              </Card>
            ) : null}

            {report.inventory ? (
              <Card title="Stok" link="/panel/stok">
                <BarChart
                  title="Stok hareketleri"
                  series={[
                    { label: "Giriş", color: GREEN, points: report.inventory.movements_in },
                    { label: "Çıkış", color: VIOLET, points: report.inventory.movements_out },
                  ]}
                  format={(value) => `${count(value)} hareket`}
                />
                <RankList title="Kritik seviyedeki ürünler" items={report.inventory.low_items} empty="Kritik seviyede ürün yok." />
              </Card>
            ) : null}

            {report.projects ? (
              <Card title="Projeler" link="/panel/projeler">
                <div className="grid grid-cols-3 gap-3 text-center">
                  <Mini label="Planlanan" value={report.projects.planned} />
                  <Mini label="Aktif" value={report.projects.active} />
                  <Mini label="Tamamlanan" value={report.projects.completed} />
                </div>
                <RankList title="Teslim tarihi geçmiş aktif projeler" items={report.projects.at_risk} empty="Teslim tarihi geçmiş aktif proje yok." />
              </Card>
            ) : null}

            {report.customers ? (
              <Card title="Müşteriler" link="/panel/musteriler">
                <BarChart title="Yeni müşteriler" series={[{ label: "Yeni müşteri", color: VIOLET, points: report.customers.new }]} format={count} />
              </Card>
            ) : null}

            {report.production ? (
              <Card title="Üretim" link="/panel/uretim">
                <BarChart title="Tamamlanan iş emirleri" series={[{ label: "Tamamlanan", color: VIOLET, points: report.production.completed }]} format={count} />
              </Card>
            ) : null}
          </div>
          <p className="text-[12px] text-slate">Tutarlar TRY kayıtlarından hesaplanır; iptal edilen sipariş ve finans kayıtları dahil edilmez. Aylar şirketinizin saat dilimine göre gruplanır.</p>
        </>
      )}
    </div>
  );
}

function sum(points: { value: string }[]): number {
  return points.reduce((total, point) => total + Number(point.value), 0);
}

function Kpi({ label, value, note, tone = "text-graphite" }: { label: string; value: string; note: string; tone?: string }) {
  return (
    <div className="min-w-0 rounded-2xl border border-mist/80 bg-surface px-4 py-4">
      <p className="text-[12px] font-medium text-slate">{label}</p>
      <p className={`mt-1 truncate text-[22px] font-semibold tabular-nums tracking-tight ${tone}`}>{value}</p>
      <p className="mt-0.5 truncate text-[12px] text-slate">{note}</p>
    </div>
  );
}

function Card({ title, link, children }: { title: string; link: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="min-w-0 space-y-5 rounded-2xl border border-mist/80 bg-surface p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-[15px] font-semibold">{title}</h2>
        <Link to={link} aria-label={`${title} modülüne git`} className="text-[13px] font-semibold text-violet hover:underline">
          Modüle git
        </Link>
      </div>
      {children}
    </section>
  );
}

function RankList({ title, items, empty, format, bars = false }: { title: string; items: Ranked[]; empty: string; format?: (value: string) => string; bars?: boolean }) {
  const max = Math.max(...items.map((item) => Number(item.value)), 0);
  return (
    <div className="min-w-0">
      <h3 className="text-[13px] font-semibold text-slate">{title}</h3>
      {items.length === 0 ? (
        <p className="mt-2 text-[13px] text-slate">{empty}</p>
      ) : (
        <ol className="mt-2 space-y-2">
          {items.map((item) => (
            <li key={item.label} className="min-w-0">
              <div className="flex items-baseline justify-between gap-3 text-[13px]">
                <span className="truncate font-medium">{item.label}</span>
                <span className="shrink-0 tabular-nums text-slate">
                  {format ? format(item.value) : item.value}
                  {item.detail ? ` · ${item.detail}` : ""}
                </span>
              </div>
              {bars && max > 0 ? (
                <div aria-hidden className="mt-1 h-1.5 overflow-hidden rounded-full bg-mist/60">
                  <div className="h-full rounded-full bg-error/60" style={{ width: `${(Number(item.value) / max) * 100}%` }} />
                </div>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function Row({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-slate">{label}</dt>
      <dd className="text-right tabular-nums">
        {value}
        {note ? <span className="block text-[12px] font-medium text-error-text">{note}</span> : null}
      </dd>
    </div>
  );
}

function Mini({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl bg-cloud px-3 py-3">
      <p className="text-[20px] font-semibold tabular-nums">{count(value)}</p>
      <p className="text-[12px] text-slate">{label}</p>
    </div>
  );
}
