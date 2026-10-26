import { ApiRequestError, getJson, isRecord, postJson, sendJson } from "./http.ts";

export type ProductionStatus = "planned" | "in_progress" | "completed" | "cancelled";
export type ProductionSort = "-created_at" | "planned_date" | "number";

export type ProductionSummaryItem = {
  id: string;
  number: number;
  code: string;
  product_id: string;
  product_name: string;
  product_sku: string;
  unit: string;
  quantity: string;
  status: ProductionStatus;
  planned_date: string | null;
  material_count: number;
  shortage: boolean;
  sales_order_id: string | null;
  sales_order_code: string | null;
  project_id: string | null;
  project_name: string | null;
  created_at: string;
};

export type RecipeLine = { product_id: string; name: string; sku: string; unit: string; quantity: string; deleted: boolean };
export type Recipe = { product_id: string; name: string; unit: string; items: RecipeLine[] };
export type RecipeSummary = { product_id: string; name: string; sku: string; unit: string; materials: number };

export async function fetchRecipes(): Promise<RecipeSummary[]> {
  const payload = await getJson("/api/v1/production/recipes");
  if (!Array.isArray(payload)) throw new ApiRequestError(500, "Reçeteler okunamadı.");
  return payload as RecipeSummary[];
}

export async function fetchRecipe(productId: string): Promise<Recipe> {
  const payload = await getJson(`/api/v1/production/recipes/${productId}`);
  if (!isRecord(payload) || !Array.isArray(payload.items)) throw new ApiRequestError(500, "Reçete okunamadı.");
  return payload as Recipe;
}

export async function saveRecipe(productId: string, items: { product_id: string; quantity: string }[]): Promise<Recipe> {
  return (await sendJson("PUT", `/api/v1/production/recipes/${productId}`, { items })) as Recipe;
}

export type MaterialLine = { product_id: string; name: string; sku: string; unit: string; quantity: string; available: string; short: boolean };

export type ProductionDetail = ProductionSummaryItem & {
  note: string | null;
  cancel_reason: string | null;
  product_stock: string;
  stock_posted: boolean;
  started_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  created_by: string | null;
  materials: MaterialLine[];
};

export type ProductionPage = { items: ProductionSummaryItem[]; total: number; page: number; page_size: number };
export type ProductionSummary = Record<ProductionStatus, number>;
export type ProductionPayload = {
  product_id: string;
  quantity: string;
  planned_date: string | null;
  note: string;
  materials: { product_id: string; quantity: string }[];
};

export const productionStatusLabels: Record<ProductionStatus, string> = {
  planned: "Planlandı",
  in_progress: "Üretimde",
  completed: "Tamamlandı",
  cancelled: "İptal edildi",
};

export const productionStatusTone: Record<ProductionStatus, string> = {
  planned: "bg-cloud text-slate ring-1 ring-inset ring-mist",
  in_progress: "bg-violet/10 text-violet",
  completed: "bg-success/10 text-success-text",
  cancelled: "bg-error/[0.07] text-error-text",
};

export const productionSortLabels: Record<ProductionSort, string> = {
  "-created_at": "En yeni",
  planned_date: "Plan tarihi",
  number: "İş emri numarası",
};

export async function fetchProductionOrders(options: { q?: string; status?: ProductionStatus | null; sort?: ProductionSort; page?: number; pageSize?: number }): Promise<ProductionPage> {
  const params = new URLSearchParams();
  if (options.q) params.set("q", options.q);
  if (options.status) params.set("status", options.status);
  if (options.sort) params.set("sort", options.sort);
  if (options.page) params.set("page", String(options.page));
  if (options.pageSize) params.set("page_size", String(options.pageSize));
  const payload = await getJson(`/api/v1/production/orders?${params.toString()}`);
  if (!isRecord(payload) || !Array.isArray(payload.items) || typeof payload.total !== "number") throw new ApiRequestError(500, "İş emri listesi okunamadı.");
  return payload as ProductionPage;
}

export async function fetchProductionSummary(): Promise<ProductionSummary> {
  const payload = await getJson("/api/v1/production/summary");
  if (!isRecord(payload) || typeof payload.planned !== "number") throw new ApiRequestError(500, "Üretim özeti okunamadı.");
  return payload as ProductionSummary;
}

export async function fetchProductionOrder(id: string): Promise<ProductionDetail> {
  return readDetail(await getJson(`/api/v1/production/orders/${id}`));
}

export async function createProductionOrder(payload: ProductionPayload): Promise<ProductionDetail> {
  return readDetail(await postJson("/api/v1/production/orders", payload));
}

export async function updateProductionOrder(id: string, payload: ProductionPayload): Promise<ProductionDetail> {
  return readDetail(await sendJson("PUT", `/api/v1/production/orders/${id}`, payload));
}

export async function startProductionOrder(id: string): Promise<ProductionDetail> {
  return readDetail(await postJson(`/api/v1/production/orders/${id}/start`, undefined));
}

export async function completeProductionOrder(id: string): Promise<ProductionDetail> {
  return readDetail(await postJson(`/api/v1/production/orders/${id}/complete`, undefined));
}

export async function cancelProductionOrder(id: string, reason: string): Promise<ProductionDetail> {
  return readDetail(await postJson(`/api/v1/production/orders/${id}/cancel`, { reason }));
}

function readDetail(payload: unknown): ProductionDetail {
  if (!isRecord(payload) || typeof payload.id !== "string" || !Array.isArray(payload.materials)) throw new ApiRequestError(500, "İş emri okunamadı.");
  return payload as ProductionDetail;
}
