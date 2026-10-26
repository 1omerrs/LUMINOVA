import { useEffect, useState, type FormEvent } from "react";
import { ApiRequestError } from "../../lib/http.ts";
import {
  changeRole,
  describePermissions,
  fetchTeam,
  inviteMember,
  mailStatusLabels,
  removeMember,
  revokeInvitation,
  roleHints,
  roleLabels,
  savePermissions,
  type InvitationCreated,
  type Permissions,
  type Team,
  type TeamMember,
} from "../../lib/team.ts";
import { JoinRequests } from "./JoinRequests.tsx";
import { PermissionPicker } from "./PermissionPicker.tsx";
import { emailPattern } from "../../lib/validation.ts";
import { useWorkspace } from "../../lib/workspace.ts";
import { Alert, Button, Field, Spinner } from "../forms/Controls.tsx";
import { ConfirmDialog } from "../ui/ConfirmDialog.tsx";

const dateFormat = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "long", year: "numeric" });

export function TeamPanel() {
  const { user } = useWorkspace();
  const [team, setTeam] = useState<Team | null>(null);
  const [loadError, setLoadError] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"admin" | "member">("member");
  const [emailError, setEmailError] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState<InvitationCreated | null>(null);
  const [copied, setCopied] = useState(false);
  const [removing, setRemoving] = useState<TeamMember | null>(null);
  const [grants, setGrants] = useState<Permissions>({});
  const [editing, setEditing] = useState<{ userId: string; value: Permissions } | null>(null);
  const [saving, setSaving] = useState(false);
  const owner = user.role === "owner";

  async function savePeople() {
    if (!editing) return;
    setSaving(true);
    setError("");
    try {
      setTeam(await savePermissions(editing.userId, editing.value));
      setEditing(null);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Yetkiler kaydedilemedi.");
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    fetchTeam()
      .then((next) => {
        if (!cancelled) setTeam(next);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setLoadError(caught instanceof ApiRequestError ? caught.message : "Ekip yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function onInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setCreated(null);
    setCopied(false);
    if (!emailPattern.test(email.trim())) {
      setEmailError("Geçerli bir e-posta adresi girin.");
      return;
    }
    setPending(true);
    try {
      const result = await inviteMember(email.trim(), role, grants);
      setCreated(result);
      setEmail("");
      setGrants({});
      setTeam(await fetchTeam());
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Davet oluşturulamadı.");
    } finally {
      setPending(false);
    }
  }

  async function run(task: () => Promise<Team | void>) {
    setError("");
    try {
      const next = await task();
      setTeam(next ?? (await fetchTeam()));
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "İşlem tamamlanamadı.");
    }
  }

  const link = created?.invite_path ? `${window.location.origin}${created.invite_path}` : null;

  return (
    <section id="ekip" aria-labelledby="ekip-title" className="scroll-mt-24 rounded-2xl border border-mist/80 bg-surface px-5 py-5 sm:px-6">
      <h2 id="ekip-title" className="text-[16px] font-semibold">
        Ekip
      </h2>
      <p className="mt-1 text-[13px] leading-5 text-slate">Çalışma alanınıza ekip arkadaşlarınızı davet edin. Her hesap tek bir çalışma alanına üye olabilir.</p>

      {loadError ? (
        <div className="mt-4">
          <Alert tone="error">{loadError}</Alert>
        </div>
      ) : !team ? (
        <p role="status" className="mt-4 flex items-center gap-2.5 text-[14px] text-slate">
          <Spinner className="h-4 w-4 text-violet" /> Ekip yükleniyor.
        </p>
      ) : (
        <div className="mt-4 space-y-5">
          {team.can_manage && team.join_code ? <JoinRequests team={team} onTeam={setTeam} onError={setError} /> : null}
          <ul className="divide-y divide-mist/60 rounded-xl border border-mist/70">
            {team.members.map((person) => (
              <li key={person.user_id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[14px] font-medium">
                    {person.name}
                    {person.me ? <span className="text-slate"> (siz)</span> : null}
                  </span>
                  <span className="block truncate text-[12px] text-slate">
                    {person.email} · {dateFormat.format(new Date(person.joined_at))} tarihinden beri
                  </span>
                  {person.role === "member" && person.permissions ? (
                    <span className="mt-0.5 block text-[12px] leading-5 text-slate">
                      <span className="font-medium text-graphite">Erişim:</span> {describePermissions(person.permissions, team.grantable)}
                    </span>
                  ) : null}
                </span>
                {team.can_manage && person.role === "member" ? (
                  <Button
                    variant="quiet"
                    onClick={() => setEditing(editing?.userId === person.user_id ? null : { userId: person.user_id, value: { ...(person.permissions ?? {}) } })}
                  >
                    Yetkiler
                  </Button>
                ) : null}
                {owner && person.role !== "owner" ? (
                  <select
                    aria-label={`${person.name} rolü`}
                    value={person.role}
                    onChange={(event) => void run(() => changeRole(person.user_id, event.target.value as "admin" | "member"))}
                    className="h-9 rounded-lg border border-mist bg-surface px-2.5 text-[13px] outline-none focus:border-violet"
                  >
                    <option value="member">Üye</option>
                    <option value="admin">Yönetici</option>
                  </select>
                ) : (
                  <span className={`rounded-full px-2.5 py-0.5 text-[12px] font-semibold ${person.role === "owner" ? "bg-violet/10 text-violet" : "bg-cloud text-slate ring-1 ring-inset ring-mist"}`}>
                    {roleLabels[person.role]}
                  </span>
                )}
                {team.can_manage && !person.me && person.role !== "owner" && (owner || person.role === "member") ? (
                  <Button variant="quiet" className="text-error-text" onClick={() => setRemoving(person)}>
                    Çıkar
                  </Button>
                ) : null}
                {editing?.userId === person.user_id ? (
                  <div className="basis-full space-y-3 pt-1">
                    <PermissionPicker grantable={team.grantable} value={editing.value} disabled={saving} onChange={(value) => setEditing({ userId: person.user_id, value })} />
                    <div className="flex justify-end gap-2">
                      <Button variant="quiet" onClick={() => setEditing(null)} disabled={saving}>
                        Vazgeç
                      </Button>
                      <Button pending={saving} pendingLabel="Kaydediliyor" onClick={() => void savePeople()}>
                        Yetkileri kaydet
                      </Button>
                    </div>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>

          {error ? <Alert tone="error">{error}</Alert> : null}

          {team.can_manage ? (
            <>
              <form onSubmit={(event) => void onInvite(event)} noValidate className="grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,1fr)_150px_auto] sm:items-end">
                <Field
                  label="Davet edilecek e-posta"
                  name="invite-email"
                  type="email"
                  inputMode="email"
                  autoComplete="off"
                  value={email}
                  error={emailError}
                  onValue={(value) => {
                    setEmail(value);
                    setEmailError("");
                  }}
                />
                <div>
                  <label htmlFor="invite-role" className="text-[13px] font-medium text-graphite">
                    Rol
                  </label>
                  <select
                    id="invite-role"
                    value={role}
                    onChange={(event) => setRole(event.target.value as "admin" | "member")}
                    className="mt-1.5 h-11 w-full rounded-lg border border-mist bg-surface px-3 text-[15px] outline-none focus:border-violet"
                  >
                    <option value="member">Üye</option>
                    {owner ? <option value="admin">Yönetici</option> : null}
                  </select>
                </div>
                <Button type="submit" size="lg" pending={pending} pendingLabel="Oluşturuluyor">
                  Davet oluştur
                </Button>
                <p className="text-[12px] text-slate sm:col-span-3">{roleHints[role]}</p>
                {role === "member" ? (
                  <div className="sm:col-span-3">
                    <p className="mb-2 text-[13px] font-medium text-graphite">Üyenin erişebileceği modüller</p>
                    <PermissionPicker grantable={team.grantable} value={grants} onChange={setGrants} />
                  </div>
                ) : null}
              </form>

              {created ? (
                <div className="space-y-3 rounded-xl border border-violet/25 bg-violet/[0.03] p-4">
                  <p className="text-[13px] leading-5">{created.message}</p>
                  {link ? (
                    <div className="flex flex-col gap-2 sm:flex-row">
                      <input readOnly value={link} aria-label="Davet bağlantısı" className="h-10 min-w-0 flex-1 rounded-lg border border-mist bg-surface px-3 font-mono text-[12px]" onFocus={(event) => event.target.select()} />
                      <Button
                        variant="quiet"
                        onClick={() =>
                          void navigator.clipboard.writeText(link).then(
                            () => setCopied(true),
                            () => setCopied(false),
                          )
                        }
                      >
                        {copied ? "Kopyalandı" : "Bağlantıyı kopyala"}
                      </Button>
                    </div>
                  ) : created.email_queued ? null : (
                    <p className="text-[13px] text-slate">Bu ortamda bağlantı ekranda gösterilmez; e-posta servisi bağlandığında davet e-postayla gider.</p>
                  )}
                  <p className="text-[12px] text-slate">Bağlantı 7 gün geçerlidir ve bir kez kullanılabilir.</p>
                </div>
              ) : null}

              {team.invitations.length > 0 ? (
                <div>
                  <h3 className="text-[13px] font-semibold text-slate">Bekleyen davetler</h3>
                  <ul className="mt-2 divide-y divide-mist/60 rounded-xl border border-mist/70">
                    {team.invitations.map((item) => (
                      <li key={item.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[14px] font-medium">{item.email}</span>
                          <span className="block text-[12px] text-slate">
                            {roleLabels[item.role]} · {dateFormat.format(new Date(item.expires_at))} tarihine kadar geçerli
                          </span>
                          {item.role === "member" ? (
                            <span className="block text-[12px] text-slate">Erişim: {describePermissions(item.permissions, team.grantable)}</span>
                          ) : null}
                          {item.email_status ? (
                            <span
                              title={item.email_error ?? undefined}
                              className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-[11.5px] font-medium ${
                                item.email_status === "sent"
                                  ? "bg-success/10 text-success-text"
                                  : item.email_status === "failed"
                                    ? "bg-error/10 text-error-text"
                                    : "bg-cloud text-slate ring-1 ring-inset ring-mist"
                              }`}
                            >
                              {mailStatusLabels[item.email_status]}
                              {item.email_status === "failed" && item.email_error ? ` · ${item.email_error}` : ""}
                            </span>
                          ) : null}
                        </span>
                        <Button variant="quiet" onClick={() => void run(() => revokeInvitation(item.id))}>
                          Daveti iptal et
                        </Button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </>
          ) : (
            <p className="text-[13px] text-slate">Ekibi çalışma alanı sahibi veya yöneticisi yönetir.</p>
          )}
        </div>
      )}

      {removing ? (
        <ConfirmDialog
          title="Ekip üyesi çıkarılsın mı?"
          confirmLabel="Çalışma alanından çıkar"
          pendingLabel="Çıkarılıyor"
          onClose={() => setRemoving(null)}
          onConfirm={async () => {
            const next = await removeMember(removing.user_id);
            setTeam(next);
            setRemoving(null);
          }}
        >
          {removing.name} çalışma alanına erişemez ve açık oturumları kapatılır. Girdiği kayıtlar silinmez.
        </ConfirmDialog>
      ) : null}
    </section>
  );
}
