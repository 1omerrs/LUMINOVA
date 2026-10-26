import { useCallback, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { markAllNotificationsRead, markNotificationRead, timeAgo, type NotificationFeed, type WorkspaceNotification } from "../../lib/notifications.ts";
import { useDismiss } from "../../lib/useDismiss.ts";
import { Spinner } from "../forms/Controls.tsx";
import { Icon } from "../ui/Icon.tsx";

export function NotificationsMenu({ feed, onFeed }: { feed: NotificationFeed; onFeed: (feed: NotificationFeed) => void }) {
  const navigate = useNavigate();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const close = useCallback(() => setOpen(false), []);
  useDismiss(open, close, root, trigger);

  async function run(action: () => Promise<NotificationFeed>) {
    setBusy(true);
    setError("");
    try {
      onFeed(await action());
    } catch {
      setError("Bildirimler güncellenemedi.");
    } finally {
      setBusy(false);
    }
  }

  async function openItem(item: WorkspaceNotification) {
    if (!item.read) {
      await run(() => markNotificationRead(item.id));
    }
    setOpen(false);
    if (item.link) {
      await navigate(item.link);
    }
  }

  return (
    <div ref={root} className="relative">
      <button
        ref={trigger}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={feed.unread > 0 ? `Bildirimler, ${feed.unread} okunmamış` : "Bildirimler"}
        onClick={() => setOpen((current) => !current)}
        className={`relative grid h-10 w-10 place-items-center rounded-xl text-graphite transition-colors hover:bg-cloud ${open ? "bg-cloud" : ""}`}
      >
        <Icon name="bell" className="h-5 w-5" />
        {feed.unread > 0 ? (
          <span className="absolute right-1.5 top-1.5 grid h-4 min-w-4 place-items-center rounded-full bg-violet px-1 text-[10px] font-semibold leading-none text-white ring-2 ring-white">
            {feed.unread > 9 ? "9+" : feed.unread}
          </span>
        ) : null}
      </button>

      {open ? (
        <div
          role="dialog"
          aria-label="Bildirimler"
          className="absolute right-0 top-12 z-40 w-[min(380px,calc(100vw-24px))] origin-top-right animate-[pop_160ms_ease-out] overflow-hidden rounded-2xl border border-mist/80 bg-surface shadow-[0_24px_48px_-24px_rgba(32,36,50,0.35)]"
        >
          <div className="flex items-center justify-between border-b border-mist/70 px-4 py-3">
            <p className="text-[14px] font-semibold">Bildirimler</p>
            {feed.unread > 0 ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => void run(markAllNotificationsRead)}
                className="text-[13px] font-medium text-violet hover:underline disabled:opacity-50"
              >
                Tümünü okundu say
              </button>
            ) : busy ? (
              <Spinner className="h-4 w-4 text-violet" />
            ) : null}
          </div>
          {error ? <p className="px-4 pt-3 text-[13px] text-error-text">{error}</p> : null}
          {feed.items.length === 0 ? (
            <div className="px-6 py-10 text-center">
              <span className="mx-auto grid h-10 w-10 place-items-center rounded-full bg-cloud text-slate">
                <Icon name="bell" className="h-5 w-5" />
              </span>
              <p className="mt-3 text-[14px] font-medium">Henüz bildirim yok.</p>
              <p className="mt-1 text-[13px] text-slate">Çalışma alanınızdaki önemli değişiklikler burada görünür.</p>
            </div>
          ) : (
            <ul className="max-h-[420px] divide-y divide-mist/60 overflow-y-auto">
              {feed.items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => void openItem(item)}
                    className="flex w-full gap-3 px-4 py-3.5 text-left transition-colors hover:bg-cloud/70"
                  >
                    <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${item.read ? "bg-transparent" : "bg-violet"}`} aria-hidden />
                    <span className="min-w-0 flex-1">
                      <span className={`block text-[14px] ${item.read ? "text-graphite/80" : "font-semibold"}`}>{item.title}</span>
                      {item.body ? <span className="mt-0.5 block text-[13px] leading-5 text-slate">{item.body}</span> : null}
                      <span className="mt-1 block text-[12px] text-slate/80">
                        <time dateTime={item.created_at}>{timeAgo(item.created_at)}</time>
                        {item.read ? null : <span className="sr-only"> · okunmadı</span>}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
