import { ApiRequestError, getJson, isRecord, postJson, sendJson } from "./http.ts";

export type NotificationPreference = {
  category: string;
  label: string;
  description: string;
  in_app: boolean;
  in_app_available: boolean;
  email: boolean;
  email_available: boolean;
};
export type Channel = "in_app" | "email";

export async function fetchPreferences(): Promise<NotificationPreference[]> {
  return readPreferences(await getJson("/api/v1/notifications/preferences"));
}

export async function savePreference(category: string, channel: Channel, enabled: boolean): Promise<NotificationPreference[]> {
  return readPreferences(await sendJson("PUT", "/api/v1/notifications/preferences", { [channel]: { [category]: enabled } }));
}

function readPreferences(payload: unknown): NotificationPreference[] {
  if (!Array.isArray(payload)) throw new ApiRequestError(500, "Bildirim tercihleri okunamadı.");
  return payload.map((item: unknown) => {
    if (
      !isRecord(item) ||
      typeof item.category !== "string" ||
      typeof item.label !== "string" ||
      typeof item.description !== "string" ||
      typeof item.in_app !== "boolean"
    ) {
      throw new ApiRequestError(500, "Bildirim tercihleri okunamadı.");
    }
    return {
      category: item.category,
      label: item.label,
      description: item.description,
      in_app: item.in_app,
      in_app_available: item.in_app_available !== false,
      email: item.email === true,
      email_available: item.email_available === true,
    };
  });
}

export type WorkspaceNotification = {
  id: string;
  category: string;
  title: string;
  body: string | null;
  link: string | null;
  read: boolean;
  created_at: string;
};

export type NotificationFeed = { items: WorkspaceNotification[]; unread: number };

export const emptyFeed: NotificationFeed = { items: [], unread: 0 };

export async function fetchNotifications(): Promise<NotificationFeed> {
  return readFeed(await getJson("/api/v1/notifications"));
}

export async function markNotificationRead(id: string): Promise<NotificationFeed> {
  return readFeed(await postJson(`/api/v1/notifications/${id}/read`));
}

export async function markAllNotificationsRead(): Promise<NotificationFeed> {
  return readFeed(await postJson("/api/v1/notifications/read-all"));
}

export function timeAgo(iso: string, now = Date.now()): string {
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000);
  const format = new Intl.RelativeTimeFormat("tr", { numeric: "auto" });
  const steps: [Intl.RelativeTimeFormatUnit, number][] = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, size] of steps) {
    if (Math.abs(seconds) >= size) {
      return format.format(Math.round(seconds / size), unit);
    }
  }
  return "az önce";
}

function readFeed(payload: unknown): NotificationFeed {
  if (!isRecord(payload) || !Array.isArray(payload.items) || typeof payload.unread !== "number") {
    throw new ApiRequestError(500, "Bildirimler okunamadı.");
  }
  return {
    unread: payload.unread,
    items: payload.items.map((item: unknown) => {
      if (
        !isRecord(item) ||
        typeof item.id !== "string" ||
        typeof item.title !== "string" ||
        typeof item.category !== "string" ||
        typeof item.read !== "boolean" ||
        typeof item.created_at !== "string"
      ) {
        throw new ApiRequestError(500, "Bildirimler okunamadı.");
      }
      return {
        id: item.id,
        category: item.category,
        title: item.title,
        body: typeof item.body === "string" ? item.body : null,
        link: typeof item.link === "string" ? item.link : null,
        read: item.read,
        created_at: item.created_at,
      };
    }),
  };
}
