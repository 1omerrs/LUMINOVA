import { ApiRequestError, getJson, isRecord, postJson, sendJson } from "./http.ts";

export type Direction = "outbound" | "inbound";
export type EventType = { key: string; label: string; description: string };
export type Endpoint = {
  id: string;
  direction: Direction;
  name: string;
  url: string | null;
  inbound_path: string | null;
  events: string[];
  active: boolean;
  secret_hint: string;
  last_used_at: string | null;
  created_at: string;
  pending: number;
  failed: number;
};
export type EndpointCreated = { endpoint: Endpoint; secret: string };
export type EndpointPayload = { direction: Direction; name: string; url: string | null; events: string[]; active: boolean };
export type Delivery = {
  id: string;
  endpoint_id: string;
  endpoint_name: string;
  event_type: string;
  status: "pending" | "delivered" | "failed";
  attempts: number;
  last_status_code: number | null;
  last_error: string | null;
  next_attempt_at: string | null;
  delivered_at: string | null;
  created_at: string;
};

export const deliveryLabels: Record<Delivery["status"], string> = { pending: "Sırada", delivered: "İletildi", failed: "Başarısız" };
export const deliveryTones: Record<Delivery["status"], string> = {
  pending: "bg-cloud text-slate ring-1 ring-inset ring-mist/70",
  delivered: "bg-success/10 text-success-text",
  failed: "bg-error/10 text-error-text",
};

function list<T>(payload: unknown, message: string): T[] {
  if (!Array.isArray(payload)) throw new ApiRequestError(500, message);
  return payload as T[];
}

function created(payload: unknown): EndpointCreated {
  if (!isRecord(payload) || typeof payload.secret !== "string") throw new ApiRequestError(500, "Bağlantı yanıtı okunamadı.");
  return payload as EndpointCreated;
}

export async function fetchEventTypes(): Promise<EventType[]> {
  return list(await getJson("/api/v1/automation/events"), "Olay türleri okunamadı.");
}

export async function fetchEndpoints(): Promise<Endpoint[]> {
  return list(await getJson("/api/v1/automation/endpoints"), "Bağlantılar okunamadı.");
}

export async function createEndpoint(payload: EndpointPayload): Promise<EndpointCreated> {
  return created(await postJson("/api/v1/automation/endpoints", payload));
}

export async function updateEndpoint(id: string, payload: EndpointPayload): Promise<Endpoint> {
  return (await sendJson("PUT", `/api/v1/automation/endpoints/${id}`, payload)) as Endpoint;
}

export async function rotateEndpoint(id: string): Promise<EndpointCreated> {
  return created(await postJson(`/api/v1/automation/endpoints/${id}/rotate`));
}

export async function deleteEndpoint(id: string): Promise<void> {
  await sendJson("DELETE", `/api/v1/automation/endpoints/${id}`);
}

export async function testEndpoint(id: string): Promise<Delivery> {
  return (await postJson(`/api/v1/automation/endpoints/${id}/test`)) as Delivery;
}

export async function fetchDeliveries(): Promise<Delivery[]> {
  return list(await getJson("/api/v1/automation/deliveries"), "Gönderimler okunamadı.");
}

export async function retryDelivery(id: string): Promise<Delivery> {
  return (await postJson(`/api/v1/automation/deliveries/${id}/retry`)) as Delivery;
}
