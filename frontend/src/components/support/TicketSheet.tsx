import { useEffect, useState, type FormEvent } from "react";
import { ApiRequestError } from "../../lib/http.ts";
import { categoryLabels, statusLabels, statusTones, type TicketDetail } from "../../lib/support.ts";
import { Alert, Button, Spinner, TextArea } from "../forms/Controls.tsx";
import { Sheet } from "../ui/Sheet.tsx";

const stamp = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });

export function StatusBadge({ status }: { status: TicketDetail["status"] }) {
  return <span className={`inline-flex shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${statusTones[status]}`}>{statusLabels[status]}</span>;
}

export function TicketSheet({
  load,
  viewer,
  onReply,
  onCloseTicket,
  onChanged,
  onClose,
}: {
  load: () => Promise<TicketDetail>;
  viewer: "customer" | "staff";
  onReply: (body: string) => Promise<TicketDetail>;
  onCloseTicket: () => Promise<TicketDetail>;
  onChanged: (ticket: TicketDetail) => void;
  onClose: () => void;
}) {
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [body, setBody] = useState("");
  const [bodyError, setBodyError] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState<"reply" | "close" | null>(null);

  useEffect(() => {
    let cancelled = false;
    load()
      .then((next) => {
        if (!cancelled) setTicket(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiRequestError ? caught.message : "Talep yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [load]);

  async function run(kind: "reply" | "close", action: () => Promise<TicketDetail>) {
    setPending(kind);
    setError("");
    try {
      const next = await action();
      setTicket(next);
      onChanged(next);
      if (kind === "reply") setBody("");
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "İşlem tamamlanamadı.");
    } finally {
      setPending(null);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!body.trim()) {
      setBodyError("Mesajınızı yazın.");
      return;
    }
    void run("reply", () => onReply(body.trim()));
  }

  const mine = viewer === "customer" ? "customer" : "staff";

  return (
    <Sheet
      wide
      title={ticket ? `${ticket.code} · ${ticket.subject}` : "Destek talebi"}
      description={
        ticket ? (
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={ticket.status} />
            {categoryLabels[ticket.category]}
            {ticket.company_name ? ` · ${ticket.company_name}` : ""} · {ticket.created_by_name}
          </span>
        ) : undefined
      }
      busy={pending !== null}
      onClose={onClose}
      onSubmit={ticket?.can_reply ? onSubmit : undefined}
      footer={
        ticket?.can_reply ? (
          <>
            <Button type="button" variant="quiet" onClick={() => void run("close", onCloseTicket)} pending={pending === "close"} pendingLabel="Kapatılıyor" disabled={pending === "reply"}>
              Talebi kapat
            </Button>
            <Button type="submit" pending={pending === "reply"} pendingLabel="Gönderiliyor" disabled={pending === "close"}>
              {viewer === "staff" ? "Yanıtı gönder" : "Mesajı ekle"}
            </Button>
          </>
        ) : undefined
      }
    >
      {error ? (
        <div className="mb-4">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}
      {ticket === null && !error ? (
        <p className="flex items-center gap-2 text-[14px] text-slate">
          <Spinner /> Yükleniyor
        </p>
      ) : null}
      {ticket ? (
        <div className="space-y-6">
          <ol className="space-y-3" aria-label="Mesajlar">
            {ticket.messages.map((message) => (
              <li key={message.id} className={`flex ${message.author_kind === mine ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                    message.author_kind === "staff" ? "bg-violet/[0.07] ring-1 ring-inset ring-violet/15" : "bg-cloud ring-1 ring-inset ring-mist/70"
                  }`}
                >
                  <p className="text-[12px] font-semibold text-graphite">
                    {message.author_name}
                    <time dateTime={message.created_at} className="ml-2 font-normal text-slate">
                      {stamp.format(new Date(message.created_at))}
                    </time>
                  </p>
                  <p className="mt-1 whitespace-pre-wrap text-[14px] leading-6">{message.body}</p>
                </div>
              </li>
            ))}
          </ol>
          {ticket.can_reply ? (
            <div>
              <TextArea
                label={viewer === "staff" ? "Yanıtınız" : "Yeni mesaj"}
                value={body}
                onValue={(value) => {
                  setBody(value);
                  setBodyError("");
                }}
                error={bodyError}
                maxLength={5000}
                rows={4}
                hint={
                  viewer === "staff"
                    ? "Yanıt müşterinin bildirimlerine düşer. Müşteri destek e-postalarını açtıysa n8n üzerinden e-posta da gönderilir."
                    : "LUMINOVA ekibi yanıt verdiğinde bildirimlerinizde görünür."
                }
              />
            </div>
          ) : (
            <p className="rounded-xl bg-cloud px-4 py-3 text-[13px] text-slate">Bu talep kapandı. Yeni bir sorun için yeni talep açabilirsiniz.</p>
          )}
        </div>
      ) : null}
    </Sheet>
  );
}
