import { useCallback, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { fetchCurrentUser, logoutAccount, type CurrentUser } from "../../lib/auth.ts";
import { fetchModules, moduleForPath, modulePaths, moduleShortNames, type WorkspaceModule } from "../../lib/modules.ts";
import { emptyFeed, fetchNotifications, type NotificationFeed } from "../../lib/notifications.ts";
import type { WorkspaceContext } from "../../lib/workspace.ts";
import { Icon, type UiIconName } from "../ui/Icon.tsx";
import { PageStatus } from "../ui/PageStatus.tsx";
import { ModuleIcon } from "./ModuleIcon.tsx";
import { NotificationsMenu } from "./NotificationsMenu.tsx";
import { ProfileMenu } from "./ProfileMenu.tsx";

type Loaded = { user: CurrentUser; modules: WorkspaceModule[] };

const collapsedKey = "luminova.sidebar.collapsed";
const navGroups: { label: string; keys: WorkspaceModule["key"][] }[] = [
  { label: "Ticari", keys: ["customers", "sales", "finance"] },
  { label: "Operasyon", keys: ["inventory", "production"] },
  { label: "Planlama", keys: ["tasks", "projects"] },
  { label: "Analiz ve akış", keys: ["reporting", "automation"] },
];
const closureDay = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "long", year: "numeric" });

function pageTitle(pathname: string, modules: WorkspaceModule[]): string {
  if (pathname === "/panel" || pathname === "/panel/") return "Ana Sayfa";
  if (pathname.startsWith("/panel/profil")) return "Profil ve ayarlar";
  if (pathname.startsWith("/panel/aktiviteler")) return "Etkinlikler";
  if (pathname.startsWith("/panel/destek")) return "Destek";
  const key = moduleForPath(pathname.split("/")[2]);
  return modules.find((module) => module.key === key)?.name ?? "Sayfa bulunamadı";
}

export function WorkspaceShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [failure, setFailure] = useState("");
  const [feed, setFeed] = useState<NotificationFeed>(emptyFeed);
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(collapsedKey) === "1");
  const [drawerPath, setDrawerPath] = useState<string | null>(null);
  const drawerOpen = drawerPath === location.pathname;

  const refreshFeed = useCallback(async () => {
    try {
      setFeed(await fetchNotifications());
    } catch {
      return;
    }
  }, []);

  useEffect(() => {
    if (!drawerOpen) {
      return;
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawerPath(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const user = await fetchCurrentUser();
      if (cancelled) return;
      if (user === null) {
        await navigate("/giris", { replace: true });
        return;
      }
      if (user.staff_only) {
        await navigate("/yonetim", { replace: true });
        return;
      }
      if (!user.setup_completed) {
        await navigate("/kurulum", { replace: true });
        return;
      }
      const [modules, notifications] = await Promise.all([fetchModules(), fetchNotifications()]);
      if (!cancelled) {
        setLoaded({ user, modules });
        setFeed(notifications);
      }
    })().catch(() => {
      if (!cancelled) setFailure("Çalışma alanı yüklenemedi.");
    });
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  if (!loaded) {
    return <PageStatus message={failure || "Çalışma alanınız hazırlanıyor."} failed={Boolean(failure)} />;
  }

  function toggleCollapsed() {
    setCollapsed((current) => {
      localStorage.setItem(collapsedKey, current ? "0" : "1");
      return !current;
    });
  }

  async function onLogout() {
    await logoutAccount();
    await navigate("/giris", { replace: true });
  }

  const context: WorkspaceContext = {
    user: loaded.user,
    modules: loaded.modules,
    replaceModules: (modules) => setLoaded((current) => (current ? { ...current, modules } : current)),
    feed,
    refreshFeed,
  };
  const enabled = loaded.modules.filter((module) => module.enabled);
  const title = pageTitle(location.pathname, loaded.modules);

  const enabledKeys = new Set(enabled.map((module) => module.key));
  const groups = navGroups
    .map((group) => ({ ...group, modules: group.keys.filter((key) => enabledKeys.has(key)).map((key) => loaded.modules.find((module) => module.key === key)!) }))
    .filter((group) => group.modules.length > 0);

  const navigation = (narrow: boolean) => (
    <div className="flex h-full flex-col">
      <div className={`flex h-14 shrink-0 items-center gap-2.5 ${narrow ? "justify-center" : "px-4"}`}>
        <Link to="/panel" aria-label="LUMINOVA ana sayfa" className="flex min-w-0 items-center gap-2.5">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-surface text-[13px] font-bold text-midnight">{loaded.user.company_name.charAt(0).toLocaleUpperCase("tr-TR")}</span>
          {narrow ? null : (
            <span className="min-w-0">
              <span className="block truncate text-[13px] font-semibold leading-4 text-white">{loaded.user.company_name}</span>
              <span className="block font-display text-[9.5px] font-semibold tracking-[0.2em] text-white/40">LUMINOVA</span>
            </span>
          )}
        </Link>
      </div>
      <nav aria-label="Ana menü" className="flex-1 overflow-y-auto px-2.5 pb-4 pt-2">
        <div className="space-y-px">
          <SideLink to="/panel" end narrow={narrow} icon={{ ui: "home" }} label="Ana Sayfa" />
          <SideLink to="/panel/aktiviteler" narrow={narrow} icon={{ ui: "activity" }} label="Etkinlikler" />
        </div>
        {groups.map((group) => (
          <div key={group.label} className="mt-5">
            {narrow ? <div className="mx-3 mb-2 h-px bg-white/10" /> : <p className="mb-1.5 px-2.5 text-[10.5px] font-medium uppercase tracking-[0.12em] text-white/35">{group.label}</p>}
            <div className="space-y-px">
              {group.modules.map((module) => (
                <SideLink key={module.key} to={`/panel/${modulePaths[module.key]}`} narrow={narrow} icon={{ module: module.key }} label={moduleShortNames[module.key]} />
              ))}
            </div>
          </div>
        ))}
      </nav>
      <div className="shrink-0 space-y-px border-t border-white/[0.08] p-2.5">
        <SideLink to="/panel/destek" narrow={narrow} icon={{ ui: "help" }} label="Destek" />
        <SideLink to="/panel/profil" narrow={narrow} icon={{ ui: "settings" }} label="Ayarlar" />
      </div>
    </div>
  );

  return (
    <div className="min-h-dvh bg-cloud text-graphite">
      <aside className={`fixed inset-y-0 left-0 z-30 hidden bg-rail transition-[width] duration-200 ease-out lg:block ${collapsed ? "w-[64px]" : "w-[248px]"}`}>
        {navigation(collapsed)}
      </aside>

      {drawerOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button type="button" aria-label="Menüyü kapat" className="absolute inset-0 animate-[fade_160ms_ease-out] bg-rail/50" onClick={() => setDrawerPath(null)} />
          <aside id="panel-drawer" className="absolute inset-y-0 left-0 w-72 max-w-[85vw] animate-[drawer_200ms_ease-out] bg-rail shadow-xl">
            {navigation(false)}
          </aside>
        </div>
      ) : null}

      <div className={`transition-[padding] duration-200 ease-out ${collapsed ? "lg:pl-[64px]" : "lg:pl-[248px]"}`}>
        <header className="sticky top-0 z-20 border-b border-hairline bg-cloud/90 backdrop-blur-md">
          <div className="flex h-14 items-center gap-2 px-4 sm:px-6 lg:px-8">
            <button
              type="button"
              aria-label="Menüyü aç"
              aria-expanded={drawerOpen}
              aria-controls="panel-drawer"
              onClick={() => setDrawerPath(location.pathname)}
              className="grid h-9 w-9 place-items-center rounded-lg text-graphite hover:bg-midnight/[0.05] lg:hidden"
            >
              <Icon name="menu" />
            </button>
            <button
              type="button"
              onClick={toggleCollapsed}
              aria-label={collapsed ? "Kenar çubuğunu genişlet" : "Kenar çubuğunu daralt"}
              aria-pressed={collapsed}
              className="hidden h-8 w-8 place-items-center rounded-md text-slate transition-colors hover:bg-midnight/[0.05] hover:text-graphite lg:grid"
            >
              <Icon name="sidebar" className="h-[17px] w-[17px]" />
            </button>
            <nav aria-label="Konum" className="flex min-w-0 flex-1 items-center gap-1.5 text-[13px]">
              <span className="hidden truncate text-slate sm:inline">{loaded.user.company_name}</span>
              <span aria-hidden className="hidden text-mist sm:inline">/</span>
              <span className="truncate font-medium text-graphite">{title}</span>
            </nav>
            <div className="flex items-center gap-1">
              <NotificationsMenu feed={feed} onFeed={setFeed} />
              <ProfileMenu user={loaded.user} onLogout={onLogout} />
            </div>
          </div>
        </header>

        {loaded.user.closure_scheduled_for ? (
          <div role="status" className="border-b border-warning/30 bg-warning/10 px-4 py-2.5 text-center text-[13px] text-warning-text sm:px-6">
            Bu çalışma alanı için kapatma talebi var; {closureDay.format(new Date(loaded.user.closure_scheduled_for))} tarihinde kapanacak.{" "}
            {loaded.user.role === "owner" ? (
              <Link to="/panel/profil#veri" className="font-semibold underline">
                Talebi görüntüle
              </Link>
            ) : (
              "Sorularınız için çalışma alanı sahibiyle görüşün."
            )}
          </div>
        ) : null}

        <main className="mx-auto w-full max-w-[1280px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <div key={location.pathname} className="animate-[rise_180ms_ease-out]">
            <Outlet context={context} />
          </div>
        </main>
      </div>
    </div>
  );
}

function SideLink({
  to,
  end = false,
  narrow,
  icon,
  label,
}: {
  to: string;
  end?: boolean;
  narrow: boolean;
  icon: { ui: UiIconName } | { module: WorkspaceModule["key"] };
  label: string;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      title={narrow ? label : undefined}
      aria-label={narrow ? label : undefined}
      className={({ isActive }) =>
        `group relative flex h-8 items-center gap-2.5 rounded-md text-[13px] transition-colors ${narrow ? "justify-center" : "px-2.5"} ${
          isActive ? "bg-white/[0.09] font-medium text-white" : "text-white/60 hover:bg-white/[0.05] hover:text-white/90"
        }`
      }
    >
      {({ isActive }) => (
        <>
          {isActive ? <span aria-hidden className="absolute -left-2.5 top-1.5 bottom-1.5 w-[2px] rounded-r bg-lavender" /> : null}
          {"ui" in icon ? (
            <Icon name={icon.ui} className={`h-[16px] w-[16px] shrink-0 ${isActive ? "text-lavender" : ""}`} />
          ) : (
            <ModuleIcon name={icon.module} className={`h-[16px] w-[16px] shrink-0 ${isActive ? "text-lavender" : ""}`} />
          )}
          {narrow ? null : <span className="truncate">{label}</span>}
        </>
      )}
    </NavLink>
  );
}
