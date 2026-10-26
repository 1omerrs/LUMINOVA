import { useEffect, useState } from "react";
import { ApiRequestError } from "../../lib/http.ts";
import { fetchPreferences, savePreference, type Channel, type NotificationPreference } from "../../lib/notifications.ts";
import { Alert, Spinner } from "../forms/Controls.tsx";

const channelLabels: Record<Channel, string> = { in_app: "uygulama içi", email: "e-posta" };

export function NotificationPreferencesPanel() {
  const [items, setItems] = useState<NotificationPreference[] | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState<string | null>(null);
  const [saved, setSaved] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchPreferences()
      .then((next) => {
        if (!cancelled) setItems(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiRequestError ? caught.message : "Bildirim tercihleri yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function toggle(item: NotificationPreference, channel: Channel) {
    const next = !item[channel];
    setSaving(`${item.category}:${channel}`);
    setError("");
    setSaved("");
    setItems((current) => current?.map((entry) => (entry.category === item.category ? { ...entry, [channel]: next } : entry)) ?? current);
    try {
      setItems(await savePreference(item.category, channel, next));
      setSaved(`${item.label} ${channelLabels[channel]} bildirimleri ${next ? "açıldı" : "kapatıldı"}.`);
    } catch (caught) {
      setItems((current) => current?.map((entry) => (entry.category === item.category ? { ...entry, [channel]: item[channel] } : entry)) ?? current);
      setError(caught instanceof ApiRequestError ? caught.message : "Tercih kaydedilemedi.");
    } finally {
      setSaving(null);
    }
  }

  const emailAvailable = items?.some((item) => item.email_available) ?? false;

  return (
    <section id="bildirimler" aria-labelledby="bildirimler-title" className="scroll-mt-24 rounded-2xl border border-mist/80 bg-surface px-5 py-5 sm:px-6">
      <h2 id="bildirimler-title" className="text-[15px] font-semibold">
        Bildirimler
      </h2>
      <p className="mt-0.5 text-[13px] text-slate">Hangi bildirimleri uygulama içinde, hangilerini e-postayla almak istediğinizi seçin. Tercihler yalnızca sizin hesabınız için geçerlidir.</p>
      <div className="mt-4">
        {items === null && !error ? (
          <p className="flex items-center gap-2 py-3 text-[13px] text-slate">
            <Spinner /> Yükleniyor
          </p>
        ) : null}
        {items ? (
          <>
            <div className="flex justify-end gap-2 pb-1 text-[11px] font-semibold uppercase tracking-[0.04em] text-slate">
              <span className="w-[72px] whitespace-nowrap text-center">Uygulama</span>
              <span className="w-[72px] whitespace-nowrap text-center">E-posta</span>
            </div>
            <ul className="divide-y divide-mist/60">
              {items.map((item) => (
                <li key={item.category} className="flex items-center gap-2 py-3.5">
                  <span className="min-w-0 flex-1">
                    <span className="block text-[14px] font-semibold">{item.label}</span>
                    <span id={`pref-${item.category}`} className="mt-0.5 block text-[13px] leading-5 text-slate">
                      {item.description}
                    </span>
                  </span>
                  {(["in_app", "email"] as const).map((channel) =>
                    channel === "in_app" && !item.in_app_available ? (
                      <span key={channel} className="w-[72px] shrink-0 text-center text-[12px] text-slate">
                        Yalnızca e-posta
                      </span>
                    ) : (
                      <span key={channel} className="flex w-[72px] shrink-0 justify-center">
                        <Switch
                          checked={item[channel]}
                          disabled={channel === "email" && !item.email_available}
                          busy={saving === `${item.category}:${channel}`}
                          label={`${item.label} ${channelLabels[channel]} bildirimleri`}
                          describedBy={`pref-${item.category}`}
                          onToggle={() => (saving ? undefined : void toggle(item, channel))}
                        />
                      </span>
                    ),
                  )}
                </li>
              ))}
            </ul>
          </>
        ) : null}
        <div className="mt-3 space-y-3 border-t border-mist/60 pt-4">
          {error ? <Alert tone="error">{error}</Alert> : null}
          <p className="text-[13px] text-slate" aria-live="polite">
            {saved}
          </p>
          <p className="text-[13px] leading-5 text-slate">
            {emailAvailable
              ? "E-postalar n8n üzerinden gönderilir. Stok uyarıları sahip ve yöneticilerde, haftalık özet herkeste varsayılan olarak açıktır."
              : "E-posta servisi bu ortamda yapılandırılmadığı için e-posta bildirimleri şimdilik açılamaz."}{" "}
            Teslim ve vade hatırlatmaları birkaç dakikada bir hazırlanır.
          </p>
        </div>
      </div>
    </section>
  );
}

function Switch({
  checked,
  disabled,
  busy,
  label,
  describedBy,
  onToggle,
}: {
  checked: boolean;
  disabled: boolean;
  busy: boolean;
  label: string;
  describedBy: string;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      aria-describedby={describedBy}
      aria-busy={busy || undefined}
      disabled={disabled}
      onClick={onToggle}
      className={`relative h-6 w-11 shrink-0 rounded-full transition-colors duration-200 disabled:cursor-not-allowed disabled:opacity-40 ${
        checked ? "bg-violet" : "bg-[#dcd9d1] hover:bg-stone"
      }`}
    >
      <span
        aria-hidden
        className={`absolute top-0.5 h-5 w-5 rounded-full bg-surface shadow-[0_1px_3px_rgba(16,19,28,0.25)] transition-[left] duration-200 ${
          checked ? "left-[22px]" : "left-0.5"
        }`}
      />
    </button>
  );
}
