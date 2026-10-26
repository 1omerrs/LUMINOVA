import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { Alert, Button, Spinner } from "../../components/forms/Controls.tsx";
import { StatusBadge, TicketSheet } from "../../components/support/TicketSheet.tsx";
import { Icon } from "../../components/ui/Icon.tsx";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog.tsx";
import { PageStatus } from "../../components/ui/PageStatus.tsx";
import { completeClosure, fetchAdminClosures, type AdminClosure } from "../../lib/account.ts";
import { fetchMail, retryMail, type MailList } from "../../lib/mail.ts";
import { mailStatusLabels, type MailStatus } from "../../lib/team.ts";
import { CompanySheet } from "../../components/admin/CompanySheet.tsx";
import { fetchCurrentUser, logoutAccount, type CurrentUser } from "../../lib/auth.ts";
import { ApiRequestError } from "../../lib/http.ts";
import { timeAgo } from "../../lib/notifications.ts";
import {
  categoryLabels,
  fetchAdminCompanies,
  fetchAdminOverview,
  fetchStaffTicket,
  fetchStaffTickets,
  staffClose,
  staffReply,
  type AdminCompany,
  type AdminOverview,
  type TicketList,
  type TicketStatus,
} from "../../lib/support.ts";

const sections = [
  { id: "genel", label: "Genel bakış" },
  { id: "destek", label: "Destek talepleri" },
  { id: "sirketler", label: "Şirketler" },
  { id: "eposta", label: "E-posta" },
] as const;
type Section = (typeof sections)[number]["id"];
const dateFormat = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "short", year: "numeric" });

export function AdminPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [user, setUser] = useState<CurrentUser | null | undefined>(undefined);
  const section: Section = sections.some((item) => item.id === params.get("bolum")) ? (params.get("bolum") as Section) : "genel";

  useEffect(() => {
    let cancelled = false;
    fetchCurrentUser()
      .then(async (current) => {
        if (cancelled) return;
        if (current === null) {
          await navigate("/giris", { replace: true });
          return;
        }
        setUser(current);
      })
      .catch(() => {
        if (!cancelled) setUser(null);
      });
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  if (user === undefined) return <PageStatus message="Yönetim paneli yükleniyor." />;
  if (user === null) return <PageStatus message="Yönetim paneli yüklenemedi." failed />;

  return (
    <div className="min-h-dvh bg-cloud text-graphite">
      <header className="sticky top-0 z-20 border-b border-mist/70 bg-surface/90 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-[1200px] items-center gap-4 px-4 sm:px-6 lg:px-10">
          <span className="font-display text-sm font-semibold tracking-[0.16em]">LUMINOVA</span>
          <span className="rounded-full bg-graphite px-2.5 py-1 text-[11px] font-semibold tracking-[0.06em] text-onink">YÖNETİM</span>
          <span className="flex-1" />
          <span className="hidden text-[13px] text-slate sm:block">
            {user.first_name} {user.last_name}
          </span>
          {user.staff_only ? null : (
            <Link to="/panel" className="text-[13px] font-semibold text-violet hover:underline">
              Çalışma alanına dön
            </Link>
          )}
          <button
            type="button"
            onClick={() => void logoutAccount().then(() => navigate("/giris", { replace: true }))}
            className="text-[13px] font-semibold text-slate hover:text-graphite"
          >
            Çıkış yap
          </button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1200px] px-4 py-8 sm:px-6 lg:px-10">
        {!user.is_platform_admin ? (
          <div className="mx-auto max-w-md rounded-2xl border border-mist/80 bg-surface px-6 py-10 text-center">
            <span className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-warning/10 text-warning-text">
              <Icon name="lock" />
            </span>
            <h1 className="mt-4 text-[17px] font-semibold">Bu alan yalnızca LUMINOVA ekibine açıktır.</h1>
            <p className="mt-1.5 text-[13px] text-slate">Çalışma alanınızla ilgili bir sorun için Destek sayfasından talep açabilirsiniz.</p>
            <Link to="/panel/destek" className="mt-5 inline-block text-[14px] font-semibold text-violet hover:underline">
              Destek sayfasına git
            </Link>
          </div>
        ) : (
          <div className="space-y-6">
            <div>
              <h1 className="font-display text-[22px] font-semibold tracking-[-0.02em] text-midnight sm:text-[24px]">Platform yönetimi</h1>
              <p className="mt-1 max-w-2xl text-[14px] leading-6 text-slate">
                Şirket hesaplarını ve destek taleplerini buradan izleyin. Şirketlerin iş kayıtları bu panelde gösterilmez.
              </p>
            </div>
            <nav aria-label="Yönetim bölümleri" className="flex gap-1 rounded-xl bg-surface p-1 ring-1 ring-inset ring-mist/80 sm:w-fit">
              {sections.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  aria-current={section === item.id ? "page" : undefined}
                  onClick={() => setParams({ bolum: item.id }, { replace: true })}
                  className={`flex-1 rounded-lg px-4 py-2 text-[14px] font-medium transition-colors sm:flex-none ${
                    section === item.id ? "bg-graphite text-onink" : "text-slate hover:text-graphite"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </nav>
            {section === "genel" ? <Overview onOpen={(next) => setParams({ bolum: next }, { replace: true })} /> : null}
            {section === "destek" ? <Tickets /> : null}
            {section === "sirketler" ? <Companies /> : null}
            {section === "eposta" ? <MailQueue /> : null}
          </div>
        )}
      </main>
    </div>
  );
}

function Overview({ onOpen }: { onOpen: (section: Section) => void }) {
  const [data, setData] = useState<AdminOverview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchAdminOverview()
      .then((next) => {
        if (!cancelled) setData(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiRequestError ? caught.message : "Özet yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <Alert tone="error">{error}</Alert>;
  if (!data)
    return (
      <p className="flex items-center gap-2 text-[14px] text-slate">
        <Spinner /> Yükleniyor
      </p>
    );

  const tiles: { label: string; value: number; note?: string; to?: Section; tone?: string }[] = [
    { label: "Yanıt bekleyen talep", value: data.open_tickets, to: "destek", tone: data.open_tickets > 0 ? "text-warning-text" : undefined },
    { label: "Yanıtlanan talep", value: data.answered_tickets, note: "Müşteri dönüşü bekleniyor", to: "destek" },
    { label: "Şirket", value: data.companies, note: `${data.active_companies} kurulumu tamam`, to: "sirketler" },
    { label: "Kurulum bekleyen", value: data.setup_pending, to: "sirketler" },
    { label: "Kapatma talebi", value: data.pending_closures, to: "sirketler", tone: data.pending_closures > 0 ? "text-warning-text" : undefined },
    { label: "Etkin kullanıcı", value: data.users },
    { label: "Son 30 günde kayıt", value: data.signups_30d },
  ];

  return (
    <ul className="grid grid-cols-2 gap-3 lg:grid-cols-3">
      {tiles.map((tile) => {
        const content = (
          <>
            <span className="block text-[12px] font-medium text-slate">{tile.label}</span>
            <span className={`mt-1 block text-[26px] font-semibold tabular-nums tracking-tight ${tile.tone ?? ""}`}>{tile.value}</span>
            {tile.note ? <span className="mt-0.5 block text-[12px] text-slate">{tile.note}</span> : null}
          </>
        );
        return (
          <li key={tile.label} className="rounded-2xl border border-mist/80 bg-surface">
            {tile.to ? (
              <button type="button" onClick={() => onOpen(tile.to as Section)} className="block w-full rounded-2xl px-5 py-4 text-left transition-colors hover:bg-cloud/60">
                {content}
              </button>
            ) : (
              <div className="px-5 py-4">{content}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

const ticketFilters: { value: TicketStatus | null; label: string }[] = [
  { value: "open", label: "Yanıt bekleyen" },
  { value: "answered", label: "Yanıtlanan" },
  { value: "closed", label: "Kapanan" },
  { value: null, label: "Tümü" },
];

function Tickets() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("durum");
  const status: TicketStatus | null = raw === "tumu" ? null : raw === "answered" || raw === "closed" ? raw : "open";
  const selected = params.get("talep");
  const [data, setData] = useState<{ status: TicketStatus | null; list: TicketList } | null>(null);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const current = data && data.status === status ? data.list : null;

  useEffect(() => {
    let cancelled = false;
    fetchStaffTickets(status)
      .then((list) => {
        if (!cancelled) setData({ status, list });
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiRequestError ? caught.message : "Talepler yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [status, version]);

  function update(next: Record<string, string | null>) {
    setParams(
      (previous) => {
        const merged = new URLSearchParams(previous);
        for (const [key, value] of Object.entries(next)) {
          if (value === null) merged.delete(key);
          else merged.set(key, value);
        }
        return merged;
      },
      { replace: true },
    );
  }

  const load = useCallback(() => fetchStaffTicket(selected ?? ""), [selected]);
  const counts = data?.list;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Durum">
        {ticketFilters.map((filter) => {
          const count = filter.value && counts ? counts[filter.value] : null;
          const active = status === filter.value;
          return (
            <button
              key={filter.label}
              type="button"
              aria-pressed={active}
              onClick={() => update({ durum: filter.value ?? "tumu", talep: null })}
              className={`h-9 rounded-full px-4 text-[13px] font-semibold ring-1 ring-inset transition-colors ${
                active ? "bg-graphite text-onink ring-graphite" : "bg-surface text-graphite ring-mist hover:bg-cloud"
              }`}
            >
              {filter.label}
              {count !== null ? <span className={`ml-1.5 tabular-nums ${active ? "text-white/70" : "text-slate"}`}>{count}</span> : null}
            </button>
          );
        })}
      </div>

      {error ? <Alert tone="error">{error}</Alert> : null}
      {current === null && !error ? (
        <p className="flex items-center gap-2 text-[14px] text-slate">
          <Spinner /> Yükleniyor
        </p>
      ) : null}
      {current && current.items.length === 0 ? (
        <p className="rounded-2xl border border-mist/80 bg-surface px-6 py-10 text-center text-[14px] text-slate">Bu durumda talep yok.</p>
      ) : null}
      {current && current.items.length > 0 ? (
        <ul className="divide-y divide-mist/60 overflow-hidden rounded-2xl border border-mist/80 bg-surface">
          {current.items.map((ticket) => (
            <li key={ticket.id}>
              <button type="button" onClick={() => update({ talep: ticket.id })} className="flex w-full items-center gap-4 px-5 py-4 text-left transition-colors hover:bg-cloud/60">
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="text-[12px] font-semibold text-slate">{ticket.company_name}</span>
                    <span className="text-[12px] tabular-nums text-slate">{ticket.code}</span>
                  </span>
                  <span className="mt-0.5 block truncate text-[14px] font-semibold">{ticket.subject}</span>
                  <span className="mt-0.5 block truncate text-[13px] text-slate">
                    {categoryLabels[ticket.category]} · {ticket.created_by_name} · {ticket.message_count} mesaj · son mesaj {timeAgo(ticket.last_message_at)}
                  </span>
                </span>
                <StatusBadge status={ticket.status} />
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {selected ? (
        <TicketSheet
          key={selected}
          load={load}
          viewer="staff"
          onReply={(body) => staffReply(selected, body)}
          onCloseTicket={() => staffClose(selected)}
          onChanged={() => setVersion((value) => value + 1)}
          onClose={() => update({ talep: null })}
        />
      ) : null}
    </div>
  );
}

function Closures({ onChanged }: { onChanged: () => void }) {
  const [rows, setRows] = useState<AdminClosure[] | null>(null);
  const [error, setError] = useState("");
  const [closing, setClosing] = useState<AdminClosure | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchAdminClosures()
      .then((next) => {
        if (!cancelled) setRows(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiRequestError ? caught.message : "Kapatma talepleri yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [version]);

  if (error) return <Alert tone="error">{error}</Alert>;
  if (!rows || rows.length === 0) return null;

  return (
    <section aria-labelledby="closures-title" className="rounded-2xl border border-warning/30 bg-warning/[0.06] p-5">
      <h2 id="closures-title" className="text-[14px] font-semibold">
        Bekleyen kapatma talepleri
      </h2>
      <ul className="mt-3 divide-y divide-warning/20">
        {rows.map((row) => (
          <li key={row.id} className="flex flex-wrap items-center gap-3 py-3">
            <span className="min-w-0 flex-1 basis-64">
              <span className="block text-[14px] font-semibold">{row.company_name}</span>
              <span className="block text-[12px] text-slate">
                {row.requested_by} ({row.requested_email}) · planlanan kapanış {dateFormat.format(new Date(row.scheduled_for))}
                {row.reason ? ` · “${row.reason}”` : ""}
              </span>
            </span>
            <Button variant={row.due ? "danger" : "quiet"} onClick={() => setClosing(row)}>
              {row.due ? "Kapatmayı tamamla" : "Erken kapat"}
            </Button>
          </li>
        ))}
      </ul>
      {closing ? (
        <ConfirmDialog
          title={`${closing.company_name} kapatılsın mı?`}
          confirmLabel="Çalışma alanını kapat"
          pendingLabel="Kapatılıyor"
          onClose={() => setClosing(null)}
          onConfirm={async () => {
            await completeClosure(closing.id);
            setClosing(null);
            setVersion((value) => value + 1);
            onChanged();
          }}
        >
          Tüm üyelerin erişimi biter ve açık oturumları kapanır. Kayıtlar silinmez; saklama süresi dolunca ayrıca imha edilir.
          {closing.due ? "" : " Planlanan kapanış tarihi henüz gelmedi; yalnızca sahibin açık talebi varsa erken kapatın."}
        </ConfirmDialog>
      ) : null}
    </section>
  );
}

const mailFilters: { value: MailStatus | null; label: string }[] = [
  { value: null, label: "Tümü" },
  { value: "queued", label: "Sırada" },
  { value: "handed_off", label: "n8n'e iletildi" },
  { value: "sent", label: "Gönderildi" },
  { value: "failed", label: "Başarısız" },
];
const mailTone: Record<MailStatus, string> = {
  queued: "bg-cloud text-slate ring-1 ring-inset ring-mist",
  handed_off: "bg-violet/10 text-violet",
  sent: "bg-success/10 text-success-text",
  failed: "bg-error/10 text-error-text",
};

function MailQueue() {
  const [status, setStatus] = useState<MailStatus | null>(null);
  const [data, setData] = useState<{ status: MailStatus | null; list: MailList } | null>(null);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const [retrying, setRetrying] = useState<string | null>(null);
  const current = data && data.status === status ? data.list : null;

  useEffect(() => {
    let cancelled = false;
    fetchMail(status)
      .then((list) => {
        if (!cancelled) setData({ status, list });
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiRequestError ? caught.message : "E-posta kuyruğu yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [status, version]);

  async function retry(id: string) {
    setRetrying(id);
    setError("");
    try {
      await retryMail(id);
      setVersion((value) => value + 1);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Yeniden denenemedi.");
    } finally {
      setRetrying(null);
    }
  }

  const counts = data?.list.counts ?? {};
  return (
    <div className="space-y-4">
      {current ? (
        current.configured ? (
          <Alert tone="info">
            E-postalar {current.webhook_host ?? "n8n"} adresindeki n8n iş akışına iletilir; gönderimi n8n'deki SMTP düğümü yapar. "n8n'e iletildi" durumu, n8n'in isteği aldığını
            ama gönderim sonucunu henüz bildirmediğini gösterir.
          </Alert>
        ) : (
          <Alert tone="info">E-posta kanalı yapılandırılmadı (MAIL_WEBHOOK_URL ve MAIL_WEBHOOK_SECRET). Bu ortamda e-posta kuyruğa alınmaz ve gönderilmez.</Alert>
        )
      ) : null}
      <div className="flex flex-wrap gap-2" role="group" aria-label="Durum">
        {mailFilters.map((filter) => {
          const active = status === filter.value;
          const count = filter.value ? (counts[filter.value] ?? 0) : null;
          return (
            <button
              key={filter.label}
              type="button"
              aria-pressed={active}
              onClick={() => setStatus(filter.value)}
              className={`h-9 rounded-full px-4 text-[13px] font-semibold ring-1 ring-inset transition-colors ${
                active ? "bg-graphite text-onink ring-graphite" : "bg-surface text-graphite ring-mist hover:bg-cloud"
              }`}
            >
              {filter.label}
              {count !== null ? <span className={`ml-1.5 tabular-nums ${active ? "text-white/70" : "text-slate"}`}>{count}</span> : null}
            </button>
          );
        })}
      </div>
      {error ? <Alert tone="error">{error}</Alert> : null}
      {current === null && !error ? (
        <p className="flex items-center gap-2 text-[14px] text-slate">
          <Spinner /> Yükleniyor
        </p>
      ) : null}
      {current && current.items.length === 0 ? (
        <p className="rounded-2xl border border-mist/80 bg-surface px-6 py-10 text-center text-[14px] text-slate">Bu durumda e-posta yok.</p>
      ) : null}
      {current && current.items.length > 0 ? (
        <ul className="divide-y divide-mist/60 overflow-hidden rounded-2xl border border-mist/80 bg-surface">
          {current.items.map((item) => (
            <li key={item.id} className="flex flex-wrap items-center gap-3 px-5 py-3.5">
              <span className="min-w-0 flex-1 basis-72">
                <span className="flex flex-wrap items-center gap-2 text-[12px] text-slate">
                  <span className="font-semibold">{item.kind_label}</span>
                  {item.company_name ? <span>{item.company_name}</span> : null}
                  <span>{timeAgo(item.created_at)}</span>
                  {item.attempts > 1 ? <span>{item.attempts} deneme</span> : null}
                </span>
                <span className="mt-0.5 block truncate text-[14px] font-semibold">{item.subject}</span>
                <span className="block truncate text-[13px] text-slate">
                  {item.to_email}
                  {item.last_error ? ` · ${item.last_error}` : ""}
                </span>
              </span>
              <span className={`rounded-full px-2.5 py-0.5 text-[12px] font-semibold ${mailTone[item.status]}`}>{mailStatusLabels[item.status].replace("E-posta ", "")}</span>
              {item.retryable ? (
                <Button variant="quiet" pending={retrying === item.id} pendingLabel="Sıraya alınıyor" onClick={() => void retry(item.id)}>
                  Yeniden dene
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function Companies() {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<{ key: string; items: AdminCompany[]; total: number } | null>(null);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const key = `${search}|${page}|${version}`;
  const current = data?.key === key ? data : null;

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(query);
      setPage(1);
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    let cancelled = false;
    fetchAdminCompanies(search, page)
      .then((next) => {
        if (!cancelled) setData({ key, ...next });
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiRequestError ? caught.message : "Şirketler yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [key, search, page, version]);

  const pages = current ? Math.max(1, Math.ceil(current.total / 25)) : 1;

  return (
    <div className="space-y-4">
      <Closures onChanged={() => setVersion((value) => value + 1)} />
      <label className="relative block sm:max-w-sm">
        <span className="sr-only">Şirket ara</span>
        <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate" />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Şirket adı veya adresi"
          className="h-10 w-full rounded-lg border border-mist bg-surface pl-9 pr-3 text-[14px] outline-none hover:border-stone focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)]"
        />
      </label>
      {error ? <Alert tone="error">{error}</Alert> : null}
      {current === null && !error ? (
        <p className="flex items-center gap-2 text-[14px] text-slate">
          <Spinner /> Yükleniyor
        </p>
      ) : null}
      {current ? (
        <div className="overflow-x-auto rounded-2xl border border-mist/80 bg-surface">
          <table className="w-full min-w-[760px] text-left text-[13px]">
            <thead className="border-b border-mist/70 text-[12px] text-slate">
              <tr>
                <th className="px-5 py-3 font-medium">Şirket</th>
                <th className="px-3 py-3 font-medium">Sahip</th>
                <th className="px-3 py-3 text-right font-medium">Üye</th>
                <th className="px-3 py-3 text-right font-medium">Modül</th>
                <th className="px-3 py-3 font-medium">Son etkinlik</th>
                <th className="px-3 py-3 text-right font-medium">Açık talep</th>
                <th className="px-5 py-3 font-medium">Kayıt</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-mist/60">
              {current.items.map((company) => (
                <tr key={company.id} onClick={() => setOpen(company.id)} className="cursor-pointer transition-colors hover:bg-cloud/60">
                  <td className="px-5 py-3">
                    <button type="button" onClick={() => setOpen(company.id)} className="block text-left font-semibold text-violet hover:underline">
                      {company.name}
                    </button>
                    <span className="block text-[12px] text-slate">
                      {company.slug}
                      {company.setup_completed ? "" : " · kurulum bekliyor"}
                      {company.status === "closed" ? " · kapalı" : ""}
                    </span>
                  </td>
                  <td className="px-3 py-3">
                    <span className="block">{company.owner_name}</span>
                    <span className="block text-[12px] text-slate">{company.owner_email}</span>
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums">{company.members}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{company.modules}</td>
                  <td className="px-3 py-3 text-slate">{company.last_activity_at ? timeAgo(company.last_activity_at) : "Yok"}</td>
                  <td className={`px-3 py-3 text-right tabular-nums ${company.open_tickets > 0 ? "font-semibold text-warning-text" : ""}`}>{company.open_tickets}</td>
                  <td className="px-5 py-3 text-slate">{dateFormat.format(new Date(company.created_at))}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {current.items.length === 0 ? <p className="px-5 py-8 text-center text-[14px] text-slate">Aramaya uyan şirket yok.</p> : null}
        </div>
      ) : null}
      {notice ? <Alert tone="success">{notice}</Alert> : null}
      {open ? (
        <CompanySheet
          key={open}
          companyId={open}
          onClose={() => setOpen(null)}
          onMessaged={() => setVersion((value) => value + 1)}
          onDeleted={(name) => {
            setOpen(null);
            setNotice(`${name} ve ona ait tüm kayıtlar silindi.`);
            setVersion((value) => value + 1);
          }}
        />
      ) : null}
      {current && pages > 1 ? (
        <div className="flex items-center justify-between text-[13px] text-slate">
          <span>
            {current.total} şirket · sayfa {page}/{pages}
          </span>
          <div className="flex gap-2">
            <Button variant="quiet" onClick={() => setPage(page - 1)} disabled={page <= 1}>
              Önceki
            </Button>
            <Button variant="quiet" onClick={() => setPage(page + 1)} disabled={page >= pages}>
              Sonraki
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
