import { ApiRequestError, getJson, isRecord, postJson, sendJson } from "./http.ts";

export type Unit = "adet" | "kg" | "g" | "lt" | "ml" | "m" | "m2" | "paket" | "kutu";
export type MovementKind = "in" | "out" | "adjustment";
export type ProductSort = "-created_at" | "name" | "-name" | "sku" | "stock";

export type Product = {
  id: string;
  sku: string;
  name: string;
  description: string | null;
  unit: Unit;
  min_stock: string;
  critical_stock: string | null;
  critical_level: string | null;
  stock_quantity: string;
  reserved: string;
  available: string;
  incoming: string;
  low: boolean;
  critical: boolean;
  created_at: string;
  updated_at: string;
};

export type Movement = {
  id: string;
  kind: MovementKind;
  quantity: string;
  balance_after: string;
  note: string | null;
  actor: string | null;
  created_at: string;
};

export type Paged<T> = { items: T[]; total: number; page: number; page_size: number };
export type InventorySummary = { products: number; low: number; critical: number };
export type ProductDraft = {
  sku: string;
  name: string;
  unit: Unit;
  min_stock: string;
  critical_stock?: string | null;
  description: string;
  initial_stock?: string;
};

export const units: { value: Unit; label: string; short: string }[] = [
  { value: "adet", label: "Adet", short: "adet" },
  { value: "kg", label: "Kilogram", short: "kg" },
  { value: "g", label: "Gram", short: "g" },
  { value: "lt", label: "Litre", short: "lt" },
  { value: "ml", label: "Mililitre", short: "ml" },
  { value: "m", label: "Metre", short: "m" },
  { value: "m2", label: "Metrekare", short: "m²" },
  { value: "paket", label: "Paket", short: "paket" },
  { value: "kutu", label: "Kutu", short: "kutu" },
];

export const wholeUnits = new Set<Unit>(["adet", "paket", "kutu"]);

export const sortLabels: Record<ProductSort, string> = {
  "-created_at": "En yeni",
  name: "Ada göre (A–Z)",
  "-name": "Ada göre (Z–A)",
  sku: "Stok koduna göre",
  stock: "Stok (azdan çoğa)",
};

const numberFormat = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 3 });

export function unitShort(unit: Unit): string {
  return units.find((item) => item.value === unit)?.short ?? unit;
}

export function wholeUnitMessage(unit: Unit): string {
  return `${units.find((item) => item.value === unit)?.label ?? unit} biriminde tam sayı girin.`;
}

export function formatQuantity(value: string | number): string {
  return numberFormat.format(Number(value));
}

export function parseQuantity(input: string): string | null {
  const cleaned = input.trim().replace(/\s/g, "");
  if (!/^\d{1,12}([.,]\d{1,3})?$/.test(cleaned)) return null;
  return cleaned.replace(",", ".");
}

export async function fetchProducts(options: { q?: string; sort?: ProductSort; low?: boolean; page?: number; pageSize?: number }): Promise<Paged<Product>> {
  const params = new URLSearchParams();
  if (options.q) params.set("q", options.q);
  if (options.sort) params.set("sort", options.sort);
  if (options.low) params.set("low", "true");
  if (options.page) params.set("page", String(options.page));
  if (options.pageSize) params.set("page_size", String(options.pageSize));
  return readPage(await getJson(`/api/v1/inventory/products?${params.toString()}`), readProduct);
}

export type ReorderSuggestion = {
  product_id: string;
  name: string;
  sku: string;
  unit: Unit;
  stock: string;
  reserved: string;
  incoming: string;
  expected: string;
  min_stock: string;
  used_last_30_days: string;
  days_left: number | null;
  suggested: string;
  action: "produce" | "purchase";
  reasons: string[];
};

export async function fetchProduct(id: string): Promise<Product> {
  return readProduct(await getJson(`/api/v1/inventory/products/${id}`));
}

export async function fetchReorder(): Promise<ReorderSuggestion[]> {
  const payload = await getJson("/api/v1/inventory/reorder");
  if (!Array.isArray(payload)) throw new ApiRequestError(500, "Öneriler okunamadı.");
  return payload as ReorderSuggestion[];
}

export async function fetchInventorySummary(): Promise<InventorySummary> {
  const payload = await getJson("/api/v1/inventory/summary");
  if (!isRecord(payload) || typeof payload.products !== "number" || typeof payload.low !== "number") {
    throw new ApiRequestError(500, "Stok özeti okunamadı.");
  }
  return { products: payload.products, low: payload.low, critical: typeof payload.critical === "number" ? payload.critical : 0 };
}

export async function createProduct(draft: ProductDraft): Promise<Product> {
  return readProduct(await postJson("/api/v1/inventory/products", draft));
}

export async function updateProduct(id: string, draft: ProductDraft): Promise<Product> {
  return readProduct(await sendJson("PUT", `/api/v1/inventory/products/${id}`, draft));
}

export async function deleteProduct(id: string): Promise<void> {
  await sendJson("DELETE", `/api/v1/inventory/products/${id}`);
}

export async function fetchMovements(id: string, page: number): Promise<Paged<Movement>> {
  return readPage(await getJson(`/api/v1/inventory/products/${id}/movements?page=${page}&page_size=10`), readMovement);
}

export async function recordMovement(
  id: string,
  input: { kind: MovementKind; quantity: string; note: string; idempotency_key: string },
): Promise<{ product: Product; movement: Movement }> {
  const payload = await postJson(`/api/v1/inventory/products/${id}/movements`, input);
  if (!isRecord(payload)) throw new ApiRequestError(500, "Stok hareketi okunamadı.");
  return { product: readProduct(payload.product), movement: readMovement(payload.movement) };
}

function readPage<T>(payload: unknown, read: (item: unknown) => T): Paged<T> {
  if (!isRecord(payload) || !Array.isArray(payload.items) || typeof payload.total !== "number") {
    throw new ApiRequestError(500, "Liste okunamadı.");
  }
  return { items: payload.items.map(read), total: payload.total, page: Number(payload.page), page_size: Number(payload.page_size) };
}

function readProduct(item: unknown): Product {
  if (!isRecord(item) || typeof item.id !== "string" || typeof item.sku !== "string" || typeof item.name !== "string") {
    throw new ApiRequestError(500, "Ürün kaydı okunamadı.");
  }
  return {
    id: item.id,
    sku: item.sku,
    name: item.name,
    description: typeof item.description === "string" ? item.description : null,
    unit: item.unit as Unit,
    min_stock: String(item.min_stock),
    critical_stock: typeof item.critical_stock === "string" ? item.critical_stock : null,
    critical_level: typeof item.critical_level === "string" ? item.critical_level : null,
    stock_quantity: String(item.stock_quantity),
    reserved: String(item.reserved ?? "0"),
    available: String(item.available ?? item.stock_quantity),
    incoming: String(item.incoming ?? "0"),
    low: item.low === true,
    critical: item.critical === true,
    created_at: String(item.created_at),
    updated_at: String(item.updated_at),
  };
}

function readMovement(item: unknown): Movement {
  if (!isRecord(item) || typeof item.id !== "string" || typeof item.kind !== "string") {
    throw new ApiRequestError(500, "Stok hareketi okunamadı.");
  }
  return {
    id: item.id,
    kind: item.kind as MovementKind,
    quantity: String(item.quantity),
    balance_after: String(item.balance_after),
    note: typeof item.note === "string" ? item.note : null,
    actor: typeof item.actor === "string" ? item.actor : null,
    created_at: String(item.created_at),
  };
}
