import { useEffect, useState } from "react";
import { sectorOptions } from "../../lib/auth.ts";
import { ApiRequestError } from "../../lib/http.ts";
import { timeAgo } from "../../lib/notifications.ts";
import { deleteCompany, fetchAdminCompany, messageCompany, type AdminCompanyDetail } from "../../lib/support.ts";
import { roleLabels } from "../../lib/team.ts";
import { Alert, Button, Field, Spinner, TextArea } from "../forms/Controls.tsx";
import { Sheet } from "../ui/Sheet.tsx";

const dateFormat = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "long", year: "numeric" });

type Mode = "view" | "message" | "delete";

export function CompanySheet({ companyId, onClose, onDeleted, onMessaged }: { companyId: string; onClose: () => void; onDeleted: (name: string) => void; onMessaged: () => void }) {
  const [company, setCompany] = useState<AdminCompanyDetail | null>(null);
  const [loadError, setLoadError] = useState("");
  const [mode, setMode] = useState<Mode>("view");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [confirm, setConfirm] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchAdminCompany(companyId)
      .then((next) => {
        if (!cancelled) setCompany(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setLoadError(caught instanceof ApiRequestError ? caught.message : "Şirket yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  async function submit() {
    if (!company) return;
    setPending(true);
    setError("");
    try {
      if (mode === "message") {
        await messageCompany(company.id, subject.trim(), body.trim());
        setNotice("Mesaj gönderildi. Şirketin sahibi ve yöneticileri bildirim aldı; yanıtları Destek talepleri bölümüne düşer.");
        setSubject("");
        setBody("");
        setMode("view");
        onMessaged();
      } else if (mode === "delete") {
        await deleteCompany(company.id, confirm);
        onDeleted(company.name);
      }
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "İşlem tamamlanamadı.");
    } finally {
      setPending(false);
    }
  }

  const sector = sectorOptions.find((item) => item.value === company?.sector)?.label;
  const canSend = mode === "message" ? subject.trim().length > 0 && body.trim().length > 0 : mode === "delete" ? confirm.trim() === company?.name : false;

  return (
    <Sheet
      title={company?.name ?? "Şirket"}
      description={company ? `${company.slug} · ${dateFormat.format(new Date(company.created_at))} tarihinde açıldı` : undefined}
      busy={pending}
      onClose={onClose}
      footer={
        company ? (
          mode === "view" ? (
            <>
              <Button variant="quiet" className="text-error-text" onClick={() => setMode("delete")}>
                Şirketi sil
              </Button>
              <Button onClick={() => setMode("message")} disabled={company.status !== "active"}>
                Mesaj gönder
              </Button>
            </>
          ) : (
            <>
              <Button variant="quiet" onClick={() => setMode("view")} disabled={pending}>
                Vazgeç
              </Button>
              <Button
                variant={mode === "delete" ? "danger" : "primary"}
                pending={pending}
                pendingLabel={mode === "delete" ? "Siliniyor" : "Gönderiliyor"}
                disabled={!canSend}
                onClick={() => void submit()}
              >
                {mode === "delete" ? "Kalıcı olarak sil" : "Mesajı gönder"}
              </Button>
            </>
          )
        ) : undefined
      }
    >
      {loadError ? (
        <Alert tone="error">{loadError}</Alert>
      ) : !company ? (
        <p role="status" className="flex items-center gap-2.5 text-[14px] text-slate">
          <Spinner className="h-4 w-4 text-violet" /> Şirket yükleniyor.
        </p>
      ) : (
        <div className="space-y-6">
          {notice ? <Alert tone="success">{notice}</Alert> : null}
          {error ? <Alert tone="error">{error}</Alert> : null}

          {mode === "message" ? (
            <section className="space-y-4 rounded-2xl border border-violet/25 bg-violet/[0.03] p-4">
              <p className="text-[14px] font-semibold">{company.name} yöneticilerine mesaj</p>
              <Field label="Konu" value={subject} onValue={setSubject} maxLength={160} />
              <TextArea label="Mesaj" value={body} onValue={setBody} rows={6} maxLength={5000} />
              <p className="text-[12.5px] text-slate">Mesaj, şirketin Destek sayfasında bir konuşma olarak açılır ve sahip ile yöneticilere bildirim gider. Yanıtlarını buradan takip edebilirsiniz.</p>
            </section>
          ) : null}

          {mode === "delete" ? (
            <section className="space-y-3 rounded-2xl border border-error/30 bg-error/[0.04] p-4">
              <p className="text-[14px] font-semibold text-error-text">Bu işlem geri alınamaz.</p>
              <p className="text-[13px] leading-5">
                {company.name} çalışma alanına ait tüm kayıtlar (müşteriler, siparişler, finans, stok, görevler, projeler, bildirimler, destek konuşmaları) ve yalnızca bu şirkete ait{" "}
                {company.members} kullanıcı hesabı kalıcı olarak silinir. Saklama zorunluluğu olan kayıtlar varsa önce yedek alın.
              </p>
              <Field label={`Onaylamak için şirket adını yazın: ${company.name}`} value={confirm} onValue={setConfirm} autoComplete="off" />
            </section>
          ) : null}

          <dl className="grid grid-cols-2 gap-3 text-[13px] sm:grid-cols-3">
            {[
              ["Durum", company.status === "active" ? (company.setup_completed ? "Etkin" : "Kurulum bekliyor") : "Kapalı"],
              ["Sektör", sector ?? "Belirtilmedi"],
              ["Ekip büyüklüğü", company.team_size ? (company.team_size === "1" ? "Tek kişi" : `${company.team_size} kişi`) : "Belirtilmedi"],
              ["Sahip", `${company.owner_name} · ${company.owner_email}`],
              ["Son etkinlik", company.last_activity_at ? timeAgo(company.last_activity_at) : "Yok"],
              ["Açık destek talebi", String(company.open_tickets)],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl border border-mist/70 px-3 py-2.5">
                <dt className="text-[12px] text-slate">{label}</dt>
                <dd className="mt-0.5 break-words font-medium">{value}</dd>
              </div>
            ))}
          </dl>

          <section>
            <h3 className="text-[13px] font-semibold text-slate">Kullandığı modüller · {company.module_list.length}</h3>
            {company.module_list.length ? (
              <ul className="mt-2 flex flex-wrap gap-2">
                {company.module_list.map((module) => (
                  <li key={module.key} className="rounded-full bg-cloud px-3 py-1 text-[13px] ring-1 ring-inset ring-mist">
                    {module.name}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-[13px] text-slate">Henüz modül seçilmedi.</p>
            )}
            <p className="mt-2 text-[12px] text-slate">Gizlilik gereği modüllerin içindeki kayıtlar (müşteri, finans, stok vb.) bu panelde gösterilmez.</p>
          </section>

          <section>
            <h3 className="text-[13px] font-semibold text-slate">
              Ekip · {company.people.length}
              {company.pending_join_requests ? ` · ${company.pending_join_requests} onay bekleyen` : ""}
              {company.pending_invitations ? ` · ${company.pending_invitations} açık davet` : ""}
            </h3>
            <ul className="mt-2 divide-y divide-mist/60 rounded-xl border border-mist/70">
              {company.people.map((person) => (
                <li key={person.email} className="flex flex-wrap items-center gap-3 px-4 py-2.5">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[14px] font-medium">{person.name}</span>
                    <span className="block truncate text-[12px] text-slate">
                      {person.email} · {dateFormat.format(new Date(person.joined_at))}
                    </span>
                  </span>
                  <span className="rounded-full bg-cloud px-2.5 py-0.5 text-[12px] font-semibold text-slate ring-1 ring-inset ring-mist">{roleLabels[person.role]}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </Sheet>
  );
}
