import { useState } from "react";
import { ApiRequestError } from "../../lib/http.ts";
import { approveJoin, rejectJoin, renewJoinCode, type Permissions, type Team } from "../../lib/team.ts";
import { Button } from "../forms/Controls.tsx";
import { ConfirmDialog } from "../ui/ConfirmDialog.tsx";
import { PermissionPicker } from "./PermissionPicker.tsx";

const dateFormat = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });

export function JoinRequests({ team, onTeam, onError }: { team: Team; onTeam: (team: Team) => void; onError: (message: string) => void }) {
  const [approving, setApproving] = useState<{ id: string; value: Permissions } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [copied, setCopied] = useState<"code" | "link" | null>(null);
  const [renewing, setRenewing] = useState(false);
  const code = team.join_code ?? "";
  const link = `${window.location.origin}/kayit?kod=${encodeURIComponent(code)}`;

  async function run(key: string, task: () => Promise<Team>) {
    setBusy(key);
    onError("");
    try {
      onTeam(await task());
      setApproving(null);
    } catch (caught) {
      onError(caught instanceof ApiRequestError ? caught.message : "İşlem tamamlanamadı.");
    } finally {
      setBusy(null);
    }
  }

  function copy(kind: "code" | "link") {
    void navigator.clipboard.writeText(kind === "code" ? code : link).then(
      () => setCopied(kind),
      () => setCopied(null),
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-violet/25 bg-violet/[0.03] p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-[13px] font-semibold text-graphite">Katılım kodu</p>
            <p className="mt-1 font-mono text-[22px] font-semibold tracking-[0.12em]">{code}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="quiet" onClick={() => copy("code")}>
              {copied === "code" ? "Kopyalandı" : "Kodu kopyala"}
            </Button>
            <Button variant="quiet" onClick={() => copy("link")}>
              {copied === "link" ? "Kopyalandı" : "Kayıt bağlantısını kopyala"}
            </Button>
            <Button variant="quiet" onClick={() => setRenewing(true)}>
              Kodu yenile
            </Button>
          </div>
        </div>
        <p className="mt-2 text-[12.5px] leading-5 text-slate">
          Ekip arkadaşınız kayıt ekranında “Bir ekibe katılıyorum”u seçip bu kodu girer. İsteği burada onaylayıp yetkilerini seçtiğinizde giriş yapabilir.
        </p>
      </div>

      {team.join_requests.length > 0 ? (
        <div>
          <h3 className="text-[13px] font-semibold text-slate">Onay bekleyen katılım istekleri · {team.join_requests.length}</h3>
          <ul className="mt-2 divide-y divide-mist/60 rounded-xl border border-warning/30 bg-warning/[0.04]">
            {team.join_requests.map((request) => (
              <li key={request.id} className="space-y-3 px-4 py-3">
                <div className="flex flex-wrap items-start gap-3">
                  <span className="min-w-0 flex-1">
                    <span className="block text-[14px] font-medium">
                      {request.name}
                      {request.position ? <span className="font-normal text-slate"> · {request.position}</span> : null}
                    </span>
                    <span className="block text-[12px] text-slate">
                      {request.email} · {dateFormat.format(new Date(request.created_at))}
                      {request.email_verified ? "" : " · e-postasını henüz doğrulamadı"}
                    </span>
                    {request.note ? <span className="mt-1 block text-[13px] leading-5">“{request.note}”</span> : null}
                  </span>
                  {approving?.id === request.id ? null : (
                    <span className="flex gap-2">
                      <Button variant="quiet" className="text-error-text" pending={busy === `reject:${request.id}`} pendingLabel="Reddediliyor" onClick={() => void run(`reject:${request.id}`, () => rejectJoin(request.id))}>
                        Reddet
                      </Button>
                      <Button disabled={!request.email_verified} onClick={() => setApproving({ id: request.id, value: {} })}>
                        Onayla
                      </Button>
                    </span>
                  )}
                </div>
                {approving?.id === request.id ? (
                  <div className="space-y-3">
                    <p className="text-[13px] font-medium text-graphite">{request.name} hangi modülleri görebilsin?</p>
                    <PermissionPicker grantable={team.grantable} value={approving.value} onChange={(value) => setApproving({ id: request.id, value })} />
                    <div className="flex justify-end gap-2">
                      <Button variant="quiet" onClick={() => setApproving(null)}>
                        Vazgeç
                      </Button>
                      <Button pending={busy === `approve:${request.id}`} pendingLabel="Onaylanıyor" onClick={() => void run(`approve:${request.id}`, () => approveJoin(request.id, approving.value))}>
                        Onayla ve ekibe ekle
                      </Button>
                    </div>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {renewing ? (
        <ConfirmDialog
          title="Katılım kodu yenilensin mi?"
          confirmLabel="Kodu yenile"
          pendingLabel="Yenileniyor"
          onClose={() => setRenewing(false)}
          onConfirm={async () => {
            onTeam(await renewJoinCode());
            setRenewing(false);
          }}
        >
          Eski kodla artık kayıt olunamaz. Bekleyen istekler ve ekipteki kişiler etkilenmez.
        </ConfirmDialog>
      ) : null}
    </div>
  );
}
