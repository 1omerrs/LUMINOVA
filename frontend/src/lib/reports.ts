import { ApiRequestError, getJson, isRecord } from "./http.ts";

export type Point = { month: string; value: string };
export type Ranked = { label: string; value: string; detail: string | null };

export type ReportOverview = {
  today: string;
  period_from: string;
  period_to: string;
  months: string[];
  sales: {
    revenue: Point[];
    orders: Point[];
    total_revenue: string;
    order_count: number;
    average_order: string;
    open_orders: number;
    other_currency_orders: number;
    top_customers: Ranked[];
    top_products: Ranked[];
  } | null;
  finance: {
    income: Point[];
    expense: Point[];
    total_income: string;
    total_expense: string;
    net: string;
    receivable: string;
    payable: string;
    overdue_receivables: number;
    overdue_payables: number;
    expense_categories: Ranked[];
  } | null;
  inventory: { products: number; low: number; low_items: Ranked[]; movements_in: Point[]; movements_out: Point[] } | null;
  tasks: { created: Point[]; completed: Point[]; open: number; overdue: number; completion_rate: number } | null;
  projects: { active: number; planned: number; completed: number; average_progress: number; at_risk: Ranked[] } | null;
  production: { completed: Point[]; open: number; completed_total: number } | null;
  customers: { new: Point[]; total: number } | null;
};

export const periods = [3, 6, 12] as const;
export type Period = (typeof periods)[number];

const monthShort = new Intl.DateTimeFormat("tr-TR", { month: "short", timeZone: "UTC" });
const monthLong = new Intl.DateTimeFormat("tr-TR", { month: "long", year: "numeric", timeZone: "UTC" });

export function monthLabel(key: string, long = false): string {
  const [year, month] = key.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, 1));
  return (long ? monthLong : monthShort).format(date);
}

export async function fetchOverview(months: Period): Promise<ReportOverview> {
  const payload = await getJson(`/api/v1/reports/overview?months=${months}`);
  if (!isRecord(payload) || !Array.isArray(payload.months)) throw new ApiRequestError(500, "Rapor okunamadı.");
  return payload as ReportOverview;
}
