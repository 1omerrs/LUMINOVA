import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { Alert, Button, Field, Spinner, TextArea } from "../../components/forms/Controls.tsx";
import { StatusBadge, TicketSheet } from "../../components/support/TicketSheet.tsx";
import { Icon } from "../../components/ui/Icon.tsx";
import { Sheet } from "../../components/ui/Sheet.tsx";
import { ApiRequestError } from "../../lib/http.ts";
import { timeAgo } from "../../lib/notifications.ts";
import { categoryLabels, closeTicket, fetchTicket, fetchTickets, openTicket, writeMessage, type CustomerCategory, type TicketDetail, type TicketList } from "../../lib/support.ts";
import { useWorkspace } from "../../lib/workspace.ts";

const categories: CustomerCategory[] = ["question", "bug", "request", "complaint", "account"];
const selectClass =
  "mt-1.5 h-11 w-full rounded-lg border border-mist bg-surface px-3 text-[15px] text-graphite outline-none hover:border-stone focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)]";

export function SupportPage() {
  const { user, refreshFeed } = useWorkspace();
  const [params, setParams] = useSearchParams();
  const selected = params.get("talep");
  const [tickets, setTickets] = useState<TicketList | null>(null);
  const [error, setError] = useState("");
  const asked = params.get("tur");
  const [creating, setCreating] = useState<CustomerCategory | null>(() =>
    params.get("yeni") ? (categories.includes(asked as CustomerCategory) ? (asked as CustomerCategory) : "question") : null,
  );
  const manager = user.role !== "member";

  const reload = useCallback(async () => {
    try {
      setTickets(await fetchTickets());
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Talepler yüklenemedi.");
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchTickets()
      .then((next) => {
        if (!cancelled) setTickets(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiRequestError ? caught.message : "Talepler yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function select(id: string | null) {
    setParams(id ? { talep: id } : {}, { replace: true });
  }

  const load = useCallback(() => fetchTicket(selected ?? ""), [selected]);

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-[22px] font-semibold tracking-[-0.02em] text-midnight sm:text-[24px]">Destek</h1>
          <p className="mt-1 max-w-2xl text-[14px] leading-6 text-slate">
            Soru, hata ve isteklerinizi LUMINOVA ekibine iletin. Yanıtlar bu sayfada ve bildirimlerinizde görünür.
            {manager ? " Çalışma alanındaki tüm talepleri görüyorsunuz." : " Yalnızca kendi açtığınız talepleri görürsünüz."}
          </p>
        </div>
        <Button onClick={() => setCreating("question")}>
          <Icon name="plus" className="h-4 w-4" /> Yeni talep
        </Button>
      </section>

      {error ? <Alert tone="error">{error}</Alert> : null}

      {tickets === null && !error ? (
        <p className="flex items-center gap-2 text-[14px] text-slate">
          <Spinner /> Talepler yükleniyor
        </p>
      ) : null}

      {tickets && tickets.items.length === 0 ? (
        <div className="rounded-2xl border border-mist/80 bg-surface px-6 py-12 text-center">
          <span className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-paper text-ink-soft ring-1 ring-inset ring-mist">
            <Icon name="help" />
          </span>
          <p className="mt-4 text-[15px] font-semibold">Henüz destek talebiniz yok.</p>
          <p className="mt-1.5 text-[13px] text-slate">Takıldığınız bir yer olursa yeni talep açın; konuşma burada saklanır.</p>
        </div>
      ) : null}

      {tickets && tickets.items.length > 0 ? (
        <ul className="divide-y divide-mist/60 overflow-hidden rounded-2xl border border-mist/80 bg-surface">
          {tickets.items.map((ticket) => (
            <li key={ticket.id}>
              <button type="button" onClick={() => select(ticket.id)} className="flex w-full items-center gap-4 px-5 py-4 text-left transition-colors hover:bg-cloud/60">
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="text-[12px] font-semibold tabular-nums text-slate">{ticket.code}</span>
                    <span className="truncate text-[14px] font-semibold">{ticket.subject}</span>
                  </span>
                  <span className="mt-0.5 block truncate text-[13px] text-slate">
                    {categoryLabels[ticket.category]} · {ticket.opened_by_staff ? "LUMINOVA ekibi başlattı" : ticket.created_by_name} · {ticket.message_count} mesaj ·{" "}
                    {timeAgo(ticket.last_message_at)}
                  </span>
                </span>
                <StatusBadge status={ticket.status} />
                <Icon name="chevron-right" className="h-4 w-4 shrink-0 text-slate" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {creating ? (
        <NewTicket
          initialCategory={creating}
          onClose={() => setCreating(null)}
          onCreated={(ticket) => {
            setCreating(null);
            void reload();
            select(ticket.id);
          }}
        />
      ) : null}

      {selected ? (
        <TicketSheet
          key={selected}
          load={load}
          viewer="customer"
          onReply={(body) => writeMessage(selected, body)}
          onCloseTicket={() => closeTicket(selected)}
          onChanged={() => {
            void reload();
            void refreshFeed();
          }}
          onClose={() => select(null)}
        />
      ) : null}
    </div>
  );
}

function NewTicket({ initialCategory, onClose, onCreated }: { initialCategory: CustomerCategory; onClose: () => void; onCreated: (ticket: TicketDetail) => void }) {
  const [subject, setSubject] = useState("");
  const [category, setCategory] = useState<CustomerCategory>(initialCategory);
  const [body, setBody] = useState("");
  const [errors, setErrors] = useState<{ subject?: string; body?: string }>({});
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next = { subject: subject.trim() ? undefined : "Konuyu yazın.", body: body.trim() ? undefined : "Sorunu veya isteğinizi anlatın." };
    setErrors(next);
    if (next.subject || next.body) return;
    setPending(true);
    setError("");
    try {
      onCreated(await openTicket({ subject: subject.trim(), category, body: body.trim() }));
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Talep açılamadı.");
    } finally {
      setPending(false);
    }
  }

  return (
    <Sheet
      title="Yeni destek talebi"
      description="Ne olduğunu, hangi ekranda olduğunu ve ne beklediğinizi yazmanız çözümü hızlandırır."
      busy={pending}
      onClose={onClose}
      onSubmit={(event) => void onSubmit(event)}
      initialFocus="#ticket-subject"
      footer={
        <>
          <Button type="button" variant="quiet" onClick={onClose} disabled={pending}>
            Vazgeç
          </Button>
          <Button type="submit" pending={pending} pendingLabel="Gönderiliyor">
            Talebi gönder
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Field id="ticket-subject" label="Konu" value={subject} onValue={(value) => setSubject(value)} error={errors.subject} maxLength={160} />
        <div>
          <label htmlFor="ticket-category" className="text-[14px] font-medium">
            Tür
          </label>
          <select id="ticket-category" value={category} onChange={(event) => setCategory(event.target.value as CustomerCategory)} className={selectClass}>
            {categories.map((item) => (
              <option key={item} value={item}>
                {categoryLabels[item]}
              </option>
            ))}
          </select>
        </div>
        <TextArea label="Açıklama" value={body} onValue={(value) => setBody(value)} error={errors.body} maxLength={5000} rows={7} />
      </div>
    </Sheet>
  );
}
