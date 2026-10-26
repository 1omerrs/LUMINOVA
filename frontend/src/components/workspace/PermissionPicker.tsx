import { levelLabels, withDependencies, type GrantableModule, type Level, type Permissions } from "../../lib/team.ts";

export function PermissionPicker({ grantable, value, onChange, disabled = false }: { grantable: GrantableModule[]; value: Permissions; onChange: (next: Permissions) => void; disabled?: boolean }) {
  const effective = withDependencies(value, grantable);
  const names = new Map(grantable.map((item) => [item.key, item.name]));

  function choose(key: string, level: string) {
    const next = { ...value };
    if (level === "view" || level === "edit") next[key] = level as Level;
    else delete next[key];
    onChange(next);
  }

  if (grantable.length === 0) return <p className="text-[13px] text-slate">Çalışma alanında yetki verilebilecek açık bir modül yok.</p>;

  return (
    <div className="overflow-hidden rounded-xl border border-mist/70">
      <ul className="divide-y divide-mist/60">
        {grantable.map((module) => {
          const own = value[module.key];
          const implied = !own && effective[module.key];
          const needers = implied
            ? grantable.filter((other) => other.requires.includes(module.key) && effective[other.key]).map((other) => names.get(other.key) ?? other.key)
            : [];
          return (
            <li key={module.key} className="flex flex-wrap items-center gap-3 px-4 py-2.5">
              <span className="min-w-0 flex-1 basis-48">
                <span className="block text-[14px] font-medium">{module.name}</span>
                {implied ? <span className="block text-[12px] text-slate">{needers.join(", ")} için görüntüleme otomatik verilir</span> : null}
              </span>
              <select
                aria-label={`${module.name} yetkisi`}
                value={own ?? ""}
                disabled={disabled}
                onChange={(event) => choose(module.key, event.target.value)}
                className={`h-9 rounded-lg border border-mist bg-surface px-2.5 text-[13px] outline-none focus:border-violet ${own === "edit" ? "font-semibold" : ""}`}
              >
                <option value="">{implied ? `${levelLabels.view} (otomatik)` : "Erişim yok"}</option>
                <option value="view">{levelLabels.view}</option>
                <option value="edit">{levelLabels.edit}</option>
              </select>
            </li>
          );
        })}
      </ul>
      <p className="border-t border-mist/60 bg-cloud/40 px-4 py-2 text-[12px] leading-5 text-slate">
        Görüntüleme kayıtları görmeyi, düzenleme eklemeyi ve değiştirmeyi sağlar. Seçilmeyen modüller üyenin menüsünde görünmez; ana sayfa, raporlar ve etkinlikler de buna göre süzülür.
      </p>
    </div>
  );
}
