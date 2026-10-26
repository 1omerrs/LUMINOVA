import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  createEndpoint,
  deleteEndpoint,
  deliveryLabels,
  deliveryTones,
  fetchDeliveries,
  fetchEndpoints,
  fetchEventTypes,
  retryDelivery,
  rotateEndpoint,
  testEndpoint,
  updateEndpoint,
  type Delivery,
  type Direction,
  type Endpoint,
  type EndpointCreated,
  type EventType,
} from "../../lib/automation.ts";
import { ApiRequestError } from "../../lib/http.ts";
import type { WorkspaceModule } from "../../lib/modules.ts";
import { timeAgo } from "../../lib/notifications.ts";
import { useWorkspace } from "../../lib/workspace.ts";
import { Alert, Button, Field, Spinner } from "../forms/Controls.tsx";
import { ConfirmDialog } from "../ui/ConfirmDialog.tsx";
import { Icon } from "../ui/Icon.tsx";
import { Sheet } from "../ui/Sheet.tsx";

type Data = { events: EventType[]; endpoints: Endpoint[]; deliveries: Delivery[] };
type Editing = { mode: "new" } | { mode: "edit"; endpoint: Endpoint };

export function AutomationView({ module }: { module: WorkspaceModule }) {
  const { user } = useWorkspace();
  const manager = user.role !== "member";
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState<Editing | null>(null);
  const [secret, setSecret] = useState<EndpointCreated | null>(null);
  const [removing, setRemoving] = useState<Endpoint | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [events, endpoints, deliveries] = await Promise.all([fetchEventTypes(), fetchEndpoints(), fetchDeliveries()]);
    setData({ events, endpoints, deliveries });
  }, []);

  useEffect(() => {
    if (!manager) return;
    let cancelled = false;
    Promise.all([fetchEventTypes(), fetchEndpoints(), fetchDeliveries()])
      .then(([events, endpoints, deliveries]) => {
        if (!cancelled) setData({ events, endpoints, deliveries });
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiRequestError ? caught.message : "Otomasyonlar yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [manager]);

  async function run(key: string, action: () => Promise<string | void>) {
    setBusy(key);
    setError("");
    setNotice("");
    try {
      const message = await action();
      if (message) setNotice(message);
      await load();
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "İşlem tamamlanamadı.");
    } finally {
      setBusy(null);
    }
  }

  const labels = Object.fromEntries((data?.events ?? []).map((event) => [event.key, event.label]));
  const outbound = data?.endpoints.filter((item) => item.direction === "outbound") ?? [];
  const inbound = data?.endpoints.filter((item) => item.direction === "inbound") ?? [];

  return (
    <div className="space-y-8">
      <section className="flex flex-wrap items-center gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-[22px] font-semibold tracking-[-0.02em] text-midnight sm:text-[24px]">{module.name}</h1>
          <p className="mt-0.5 max-w-2xl text-[14px] text-slate">
            LUMINOVA olaylarını imzalı webhook ile n8n gibi araçlara gönderin; dış sistemlerden gelen imzalı isteklerle görev ve bildirim oluşturun.
          </p>
        </div>
        {manager ? (
          <Button onClick={() => setEditing({ mode: "new" })}>
            <Icon name="plus" className="h-4 w-4" /> Yeni bağlantı
          </Button>
        ) : null}
      </section>

      {!manager ? (
        <div className="rounded-2xl border border-mist/80 bg-surface px-6 py-10 text-center">
          <span className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-cloud text-slate ring-1 ring-inset ring-mist/70">
            <Icon name="lock" />
          </span>
          <p className="mt-4 text-[15px] font-semibold">Otomasyon bağlantılarını çalışma alanı sahibi veya yöneticisi yönetir.</p>
          <p className="mt-1.5 text-[13px] text-slate">Bağlantılar gizli anahtar içerdiği için üyelere gösterilmez.</p>
        </div>
      ) : null}

      {error ? <Alert tone="error">{error}</Alert> : null}
      {notice ? <Alert tone="info">{notice}</Alert> : null}

      {manager && data === null && !error ? (
        <p className="flex items-center gap-2 text-[14px] text-slate">
          <Spinner /> Yükleniyor
        </p>
      ) : null}

      {manager && data ? (
        <>
          <section aria-labelledby="outbound-title" className="space-y-3">
            <div>
              <h2 id="outbound-title" className="text-[15px] font-semibold">
                Giden webhook'lar
              </h2>
              <p className="mt-0.5 text-[13px] text-slate">Seçtiğiniz olay olduğunda LUMINOVA adrese imzalı bir POST isteği gönderir. Başarısız gönderimler 6 kez yeniden denenir.</p>
            </div>
            {outbound.length === 0 ? (
              <Empty text="Henüz giden bağlantı yok. n8n'deki Webhook düğümünün adresini ekleyerek başlayın." />
            ) : (
              <ul className="space-y-3">
                {outbound.map((endpoint) => (
                  <li key={endpoint.id} className="rounded-2xl border border-mist/80 bg-surface p-5">
                    <div className="flex flex-wrap items-start gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="flex flex-wrap items-center gap-2">
                          <span className="text-[15px] font-semibold">{endpoint.name}</span>
                          <Status active={endpoint.active} />
                        </p>
                        <p className="mt-1 break-all font-mono text-[12px] text-slate">{endpoint.url}</p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          variant="quiet"
                          pending={busy === `test:${endpoint.id}`}
                          pendingLabel="Gönderiliyor"
                          onClick={() =>
                            void run(`test:${endpoint.id}`, async () => {
                              const result = await testEndpoint(endpoint.id);
                              return result.status === "delivered"
                                ? `Deneme olayı iletildi (HTTP ${result.last_status_code}).`
                                : `Deneme olayı iletilemedi: ${result.last_error ?? "bilinmeyen hata"}`;
                            })
                          }
                        >
                          Deneme gönder
                        </Button>
                        <EndpointActions endpoint={endpoint} busy={busy} onEdit={() => setEditing({ mode: "edit", endpoint })} onRemove={() => setRemoving(endpoint)} onRotate={() => void run(`rotate:${endpoint.id}`, async () => setSecret(await rotateEndpoint(endpoint.id)))} />
                      </div>
                    </div>
                    <ul className="mt-3 flex flex-wrap gap-1.5">
                      {endpoint.events.map((key) => (
                        <li key={key} className="rounded-full bg-violet/[0.07] px-2.5 py-1 text-[12px] font-medium text-violet">
                          {labels[key] ?? key}
                        </li>
                      ))}
                    </ul>
                    <p className="mt-3 text-[12px] text-slate">
                      Anahtar …{endpoint.secret_hint}
                      {endpoint.last_used_at ? ` · son başarılı gönderim ${timeAgo(endpoint.last_used_at)}` : " · henüz gönderim yok"}
                      {endpoint.pending > 0 ? ` · ${endpoint.pending} sırada` : ""}
                      {endpoint.failed > 0 ? <span className="font-semibold text-error-text"> · {endpoint.failed} başarısız</span> : null}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="inbound-title" className="space-y-3">
            <div>
              <h2 id="inbound-title" className="text-[15px] font-semibold">
                Gelen webhook'lar
              </h2>
              <p className="mt-0.5 text-[13px] text-slate">
                Dış sistem bu adrese imzalı istek gönderir. Desteklenen işlemler: <code className="rounded bg-cloud px-1">task.create</code> (görev açar) ve{" "}
                <code className="rounded bg-cloud px-1">notification.create</code> (sahip ve yöneticilere bildirim düşer).
              </p>
            </div>
            {inbound.length === 0 ? (
              <Empty text="Henüz gelen bağlantı yok." />
            ) : (
              <ul className="space-y-3">
                {inbound.map((endpoint) => (
                  <li key={endpoint.id} className="rounded-2xl border border-mist/80 bg-surface p-5">
                    <div className="flex flex-wrap items-start gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="flex flex-wrap items-center gap-2">
                          <span className="text-[15px] font-semibold">{endpoint.name}</span>
                          <Status active={endpoint.active} />
                        </p>
                        <p className="mt-1 break-all font-mono text-[12px] text-slate">
                          POST {window.location.origin}
                          {endpoint.inbound_path}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <EndpointActions endpoint={endpoint} busy={busy} onEdit={() => setEditing({ mode: "edit", endpoint })} onRemove={() => setRemoving(endpoint)} onRotate={() => void run(`rotate:${endpoint.id}`, async () => setSecret(await rotateEndpoint(endpoint.id)))} />
                      </div>
                    </div>
                    <p className="mt-3 text-[12px] text-slate">
                      Anahtar …{endpoint.secret_hint}
                      {endpoint.last_used_at ? ` · son istek ${timeAgo(endpoint.last_used_at)}` : " · henüz istek gelmedi"}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="signing-title" className="rounded-2xl border border-mist/80 bg-cloud/50 p-5 text-[13px] leading-6 text-slate">
            <h2 id="signing-title" className="text-[14px] font-semibold text-graphite">
              İmza nasıl doğrulanır?
            </h2>
            <p className="mt-1">
              Her istekte <code className="rounded bg-surface px-1">X-Luminova-Timestamp</code> ve <code className="rounded bg-surface px-1">X-Luminova-Signature</code> başlıkları bulunur. İmza,{" "}
              <code className="rounded bg-surface px-1">zaman_damgası + "." + ham_gövde</code> metninin bağlantı anahtarıyla HMAC-SHA256 özetidir ve{" "}
              <code className="rounded bg-surface px-1">sha256=</code> ile başlar. 5 dakikadan eski istekleri reddedin. Gelen webhook'larda aynı kurallar geçerlidir;{" "}
              <code className="rounded bg-surface px-1">X-Luminova-Delivery</code> başlığı tekrar gönderimleri engeller.
            </p>
          </section>

          <section aria-labelledby="deliveries-title" className="space-y-3">
            <h2 id="deliveries-title" className="text-[15px] font-semibold">
              Son gönderimler
            </h2>
            {data.deliveries.length === 0 ? (
              <Empty text="Henüz gönderim yok. Bağlantıya bir olay seçip ilgili modülde kayıt oluşturduğunuzda burada görünür." />
            ) : (
              <div className="overflow-x-auto rounded-2xl border border-mist/80 bg-surface">
                <table className="w-full min-w-[640px] text-left text-[13px]">
                  <thead className="border-b border-mist/70 text-[12px] text-slate">
                    <tr>
                      <th className="px-5 py-3 font-medium">Olay</th>
                      <th className="px-3 py-3 font-medium">Bağlantı</th>
                      <th className="px-3 py-3 font-medium">Durum</th>
                      <th className="px-3 py-3 font-medium">Ayrıntı</th>
                      <th className="px-5 py-3 text-right font-medium">Zaman</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-mist/60">
                    {data.deliveries.map((delivery) => (
                      <tr key={delivery.id}>
                        <td className="px-5 py-3 font-medium">{delivery.event_type === "ping" ? "Deneme" : (labels[delivery.event_type] ?? delivery.event_type)}</td>
                        <td className="px-3 py-3 text-slate">{delivery.endpoint_name}</td>
                        <td className="px-3 py-3">
                          <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${deliveryTones[delivery.status]}`}>{deliveryLabels[delivery.status]}</span>
                        </td>
                        <td className="px-3 py-3 text-slate">
                          {delivery.status === "delivered"
                            ? `HTTP ${delivery.last_status_code}`
                            : delivery.last_error
                              ? `${delivery.last_error} (${delivery.attempts} deneme)`
                              : "İlk deneme bekleniyor"}
                          {delivery.status === "failed" ? (
                            <button
                              type="button"
                              disabled={busy !== null}
                              onClick={() =>
                                void run(`retry:${delivery.id}`, async () => {
                                  const result = await retryDelivery(delivery.id);
                                  return result.status === "delivered" ? "Gönderim iletildi." : `Gönderim yine iletilemedi: ${result.last_error ?? ""}`;
                                })
                              }
                              className="ml-2 font-semibold text-violet hover:underline disabled:opacity-50"
                            >
                              Yeniden dene
                            </button>
                          ) : null}
                        </td>
                        <td className="px-5 py-3 text-right text-slate">{timeAgo(delivery.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      ) : null}

      {editing && data ? (
        <EndpointSheet
          editing={editing}
          events={data.events}
          onClose={() => setEditing(null)}
          onSaved={async (result) => {
            setEditing(null);
            if (result) setSecret(result);
            await load();
          }}
        />
      ) : null}

      {secret ? <SecretSheet created={secret} onClose={() => setSecret(null)} /> : null}

      {removing ? (
        <ConfirmDialog
          title="Bağlantı silinsin mi?"
          confirmLabel="Bağlantıyı sil"
          pendingLabel="Siliniyor"
          onClose={() => setRemoving(null)}
          onConfirm={async () => {
            await deleteEndpoint(removing.id);
            setRemoving(null);
            await load();
          }}
        >
          “{removing.name}” kapanır ve sıradaki gönderimleri iptal edilir. Bu adrese veya bu adresten istek kabul edilmez.
        </ConfirmDialog>
      ) : null}
    </div>
  );
}

function Status({ active }: { active: boolean }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${active ? "bg-success/10 text-success-text" : "bg-cloud text-slate ring-1 ring-inset ring-mist/70"}`}>
      {active ? "Etkin" : "Duraklatıldı"}
    </span>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="rounded-2xl border border-dashed border-mist bg-surface px-5 py-6 text-center text-[13px] text-slate">{text}</p>;
}

function EndpointActions({ endpoint, busy, onEdit, onRotate, onRemove }: { endpoint: Endpoint; busy: string | null; onEdit: () => void; onRotate: () => void; onRemove: () => void }) {
  return (
    <>
      <Button variant="quiet" onClick={onEdit} aria-label={`${endpoint.name} bağlantısını düzenle`}>
        <Icon name="pencil" className="h-4 w-4" />
      </Button>
      <Button variant="quiet" onClick={onRotate} pending={busy === `rotate:${endpoint.id}`} pendingLabel="Yenileniyor">
        Anahtarı yenile
      </Button>
      <Button variant="quiet" onClick={onRemove} aria-label={`${endpoint.name} bağlantısını sil`} className="text-error-text">
        <Icon name="trash" className="h-4 w-4" />
      </Button>
    </>
  );
}

function EndpointSheet({
  editing,
  events,
  onClose,
  onSaved,
}: {
  editing: Editing;
  events: EventType[];
  onClose: () => void;
  onSaved: (created: EndpointCreated | null) => Promise<void>;
}) {
  const existing = editing.mode === "edit" ? editing.endpoint : null;
  const [direction, setDirection] = useState<Direction>(existing?.direction ?? "outbound");
  const [name, setName] = useState(existing?.name ?? "");
  const [url, setUrl] = useState(existing?.url ?? "");
  const [chosen, setChosen] = useState<Set<string>>(() => new Set(existing?.events ?? []));
  const [active, setActive] = useState(existing?.active ?? true);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (name.trim().length < 2) {
      setError("Bağlantıya en az 2 karakterlik bir ad verin.");
      return;
    }
    if (direction === "outbound" && !url.trim()) {
      setError("Webhook adresini girin.");
      return;
    }
    if (direction === "outbound" && chosen.size === 0) {
      setError("En az bir olay seçin.");
      return;
    }
    setPending(true);
    setError("");
    const payload = { direction, name: name.trim(), url: direction === "outbound" ? url.trim() : null, events: [...chosen], active };
    try {
      if (existing) {
        await updateEndpoint(existing.id, payload);
        await onSaved(null);
      } else {
        await onSaved(await createEndpoint(payload));
      }
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Bağlantı kaydedilemedi.");
      setPending(false);
    }
  }

  return (
    <Sheet
      title={existing ? "Bağlantıyı düzenle" : "Yeni bağlantı"}
      description={existing ? undefined : "Anahtar kayıttan sonra bir kez gösterilir."}
      busy={pending}
      onClose={onClose}
      onSubmit={(event) => void onSubmit(event)}
      initialFocus="#endpoint-name"
      footer={
        <>
          <Button type="button" variant="quiet" onClick={onClose} disabled={pending}>
            Vazgeç
          </Button>
          <Button type="submit" pending={pending} pendingLabel="Kaydediliyor">
            {existing ? "Kaydet" : "Bağlantıyı oluştur"}
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        {error ? <Alert tone="error">{error}</Alert> : null}
        {existing ? null : (
          <fieldset>
            <legend className="text-[14px] font-medium">Yön</legend>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {(
                [
                  ["outbound", "Giden", "LUMINOVA olay gönderir"],
                  ["inbound", "Gelen", "Dış sistem istek gönderir"],
                ] as const
              ).map(([value, label, hint]) => (
                <label
                  key={value}
                  className={`cursor-pointer rounded-xl border px-4 py-3 transition-colors ${direction === value ? "border-violet bg-violet/[0.05]" : "border-mist hover:bg-cloud"}`}
                >
                  <input type="radio" name="direction" value={value} checked={direction === value} onChange={() => setDirection(value)} className="sr-only" />
                  <span className="block text-[14px] font-semibold">{label}</span>
                  <span className="block text-[12px] text-slate">{hint}</span>
                </label>
              ))}
            </div>
          </fieldset>
        )}
        <Field id="endpoint-name" label="Ad" value={name} onValue={setName} maxLength={120} hint="Ör. n8n sipariş akışı" />
        {direction === "outbound" ? (
          <>
            <Field label="Webhook adresi" value={url} onValue={setUrl} maxLength={500} inputMode="url" placeholder="https://n8n.ornek.com/webhook/..." hint="Production ortamında yalnızca https ve herkese açık adresler kabul edilir." />
            <fieldset>
              <legend className="text-[14px] font-medium">Olaylar</legend>
              <ul className="mt-2 divide-y divide-mist/60 rounded-xl border border-mist/80">
                {events.map((item) => (
                  <li key={item.key}>
                    <label className="flex cursor-pointer items-start gap-3 px-4 py-3 hover:bg-cloud/60">
                      <input
                        type="checkbox"
                        checked={chosen.has(item.key)}
                        onChange={(event) =>
                          setChosen((current) => {
                            const next = new Set(current);
                            if (event.target.checked) next.add(item.key);
                            else next.delete(item.key);
                            return next;
                          })
                        }
                        className="mt-1 h-4 w-4 accent-[#5b47d6]"
                      />
                      <span>
                        <span className="block text-[14px] font-medium">{item.label}</span>
                        <span className="block text-[12px] text-slate">
                          <code>{item.key}</code> · {item.description}
                        </span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            </fieldset>
          </>
        ) : null}
        <label className="flex items-center gap-3 text-[14px]">
          <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} className="h-4 w-4 accent-[#5b47d6]" />
          Bağlantı etkin
        </label>
      </div>
    </Sheet>
  );
}

function SecretSheet({ created, onClose }: { created: EndpointCreated; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const inboundUrl = created.endpoint.inbound_path ? `${window.location.origin}${created.endpoint.inbound_path}` : null;
  return (
    <Sheet
      title="Bağlantı anahtarı"
      description={created.endpoint.name}
      onClose={onClose}
      footer={
        <Button type="button" onClick={onClose}>
          Anahtarı kaydettim
        </Button>
      }
    >
      <div className="space-y-4">
        <Alert tone="info">Bu anahtar bir daha gösterilmez. n8n'de imza doğrulaması için şimdi kopyalayıp güvenli bir yere kaydedin.</Alert>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input readOnly value={created.secret} aria-label="Bağlantı anahtarı" onFocus={(event) => event.target.select()} className="h-10 min-w-0 flex-1 rounded-lg border border-mist bg-surface px-3 font-mono text-[12px]" />
          <Button
            variant="quiet"
            onClick={() =>
              void navigator.clipboard.writeText(created.secret).then(
                () => setCopied(true),
                () => setCopied(false),
              )
            }
          >
            {copied ? "Kopyalandı" : "Kopyala"}
          </Button>
        </div>
        {inboundUrl ? (
          <div>
            <p className="text-[13px] font-medium">İstek adresi</p>
            <p className="mt-1 break-all rounded-xl bg-cloud px-3 py-2 font-mono text-[12px]">POST {inboundUrl}</p>
            <p className="mt-2 text-[12px] leading-5 text-slate">
              Gövde örneği: <code>{'{"action":"task.create","data":{"title":"Yeni web siparişi"}}'}</code>
            </p>
          </div>
        ) : null}
      </div>
    </Sheet>
  );
}
