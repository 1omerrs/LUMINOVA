import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { Alert, Button, Spinner } from "../../components/forms/Controls.tsx";
import { Icon } from "../../components/ui/Icon.tsx";
import { ModuleIcon } from "../../components/workspace/ModuleIcon.tsx";
import { activityDay, activityTime, fetchActivity, type ActivityItem, type ActivityPage as Page } from "../../lib/activity.ts";
import { ApiRequestError } from "../../lib/http.ts";
import { initialsOf } from "../../lib/tasks.ts";
import { useWorkspace } from "../../lib/workspace.ts";

const filterSelect =
  "h-10 rounded-lg border border-mist bg-surface px-3 text-[14px] text-graphite outline-none hover:border-stone focus:border-violet focus:shadow-[0_0_0_4px_rgba(91,71,214,0.14)]";

type Loaded = { key: string; page: Page; items: ActivityItem[] };

export function ActivityPage() {
  const { modules } = useWorkspace();
  const [params, setParams] = useSearchParams();
  const moduleFilter = params.get("modul") ?? "";
  const actorFilter = params.get("kisi") ?? "";
  const key = `${moduleFilter}|${actorFilter}`;
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState("");
  const [more, setMore] = useState(false);
  const [now] = useState(() => new Date());
  const enabled = modules.filter((module) => module.enabled && module.key !== "reporting" && module.key !== "automation");
  const current = loaded?.key === key ? loaded : null;

  useEffect(() => {
    let cancelled = false;
    fetchActivity({ module: moduleFilter, actor: actorFilter })
      .then((page) => {
        if (!cancelled) {
          setError("");
          setLoaded({ key, page, items: page.items });
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiRequestError ? caught.message : "Etkinlikler yüklenemedi.");
      });
    return () => {
      cancelled = true;
    };
  }, [key, moduleFilter, actorFilter]);

  async function loadMore() {
    if (!current?.page.next_cursor) return;
    setMore(true);
    try {
      const page = await fetchActivity({ module: moduleFilter, actor: actorFilter, cursor: current.page.next_cursor });
      setLoaded({ key, page: { ...page, actors: current.page.actors }, items: [...current.items, ...page.items] });
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Etkinlikler yüklenemedi.");
    } finally {
      setMore(false);
    }
  }

  function setParam(name: string, value: string) {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        if (value) next.set(name, value);
        else next.delete(name);
        return next;
      },
      { replace: true },
    );
  }

  const groups = useMemo(() => {
    const result: { day: string; items: ActivityItem[] }[] = [];
    for (const item of current?.items ?? []) {
      const day = activityDay(item.created_at, now);
      const last = result.at(-1);
      if (last?.day === day) last.items.push(item);
      else result.push({ day, items: [item] });
    }
    return result;
  }, [current, now]);

  const filtered = Boolean(moduleFilter || actorFilter);

  return (
    <div className="space-y-6">
      <section>
        <h1 className="font-display text-[22px] font-semibold tracking-[-0.02em] text-midnight sm:text-[24px]">Etkinlikler</h1>
        <p className="mt-1 max-w-2xl text-[14px] leading-6 text-slate">
          Çalışma alanınızda kimin neyi ne zaman değiştirdiği. Kayıtlar kalıcıdır, düzenlenemez; kapalı modüllerin etkinlikleri burada görünmez.
        </p>
      </section>

      <div className="flex flex-wrap items-center gap-2">
        <select aria-label="Modül" value={moduleFilter} onChange={(event) => setParam("modul", event.target.value)} className={filterSelect}>
          <option value="">Tüm modüller</option>
          <option value="workspace">Çalışma alanı ve ekip</option>
          {enabled.map((module) => (
            <option key={module.key} value={module.key}>
              {module.name}
            </option>
          ))}
        </select>
        <select aria-label="Kişi" value={actorFilter} onChange={(event) => setParam("kisi", event.target.value)} className={filterSelect}>
          <option value="">Herkes</option>
          {(current?.page.actors ?? loaded?.page.actors ?? []).map((actor) => (
            <option key={actor.id} value={actor.id}>
              {actor.name}
            </option>
          ))}
        </select>
        {filtered ? (
          <Button variant="quiet" onClick={() => setParams({}, { replace: true })}>
            Filtreleri temizle
          </Button>
        ) : null}
      </div>

      {error ? <Alert tone="error">{error}</Alert> : null}

      {current === null && !error ? (
        <p className="flex items-center gap-2 py-6 text-[14px] text-slate">
          <Spinner /> Etkinlikler yükleniyor
        </p>
      ) : null}

      {current && current.items.length === 0 ? (
        <div className="rounded-2xl border border-mist/80 bg-surface px-6 py-12 text-center">
          <span className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-paper text-ink-soft ring-1 ring-inset ring-mist">
            <Icon name="activity" />
          </span>
          <p className="mt-4 text-[15px] font-semibold">{filtered ? "Bu filtreye uyan etkinlik yok." : "Henüz etkinlik yok."}</p>
          <p className="mt-1.5 text-[13px] text-slate">{filtered ? "Filtreleri değiştirip yeniden deneyin." : "Kayıt ekledikçe ve değiştirdikçe burada listelenir."}</p>
        </div>
      ) : null}

      {groups.map((group) => (
        <section key={group.day} aria-label={group.day}>
          <h2 className="mb-2 text-[12px] font-semibold tracking-[0.06em] text-slate capitalize">{group.day}</h2>
          <ol className="divide-y divide-mist/60 overflow-hidden rounded-2xl border border-mist/80 bg-surface">
            {group.items.map((item) => (
              <li key={item.id} className="flex items-start gap-3 px-4 py-3.5 sm:px-5">
                <span
                  aria-hidden
                  className={`grid h-9 w-9 shrink-0 place-items-center rounded-full text-[12px] font-semibold ${
                    item.actor_id ? "bg-graphite text-onink" : "bg-cloud text-slate ring-1 ring-inset ring-mist/70"
                  }`}
                >
                  {item.actor_id ? initialsOf(item.actor_name) : "S"}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[14px] leading-5">
                    <span className="font-semibold">{item.actor_name}</span> {item.verb}
                    {item.target ? (
                      <>
                        {" "}
                        {item.link ? (
                          <Link to={item.link} className="font-medium text-violet hover:underline">
                            {item.target}
                          </Link>
                        ) : (
                          <span className="font-medium">{item.target}</span>
                        )}
                      </>
                    ) : null}
                  </p>
                  {item.detail ? <p className="mt-0.5 text-[13px] text-slate">{item.detail}</p> : null}
                </div>
                <span className="flex shrink-0 items-center gap-2 pt-0.5 text-[12px] text-slate">
                  {item.module === "workspace" ? <Icon name="settings" className="h-3.5 w-3.5" /> : <ModuleIcon name={item.module} className="h-3.5 w-3.5" />}
                  <time dateTime={item.created_at}>{activityTime(item.created_at)}</time>
                </span>
              </li>
            ))}
          </ol>
        </section>
      ))}

      {current?.page.next_cursor ? (
        <div className="flex justify-center">
          <Button variant="quiet" onClick={() => void loadMore()} pending={more} pendingLabel="Yükleniyor">
            Daha eski etkinlikleri göster
          </Button>
        </div>
      ) : null}
    </div>
  );
}
