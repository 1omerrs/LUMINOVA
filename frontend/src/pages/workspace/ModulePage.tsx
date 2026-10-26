import { useEffect, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";
import { CustomersModule } from "../../components/customers/CustomersModule.tsx";
import { InventoryView } from "../../components/inventory/InventoryView.tsx";
import { SalesView } from "../../components/sales/SalesView.tsx";
import { TasksView } from "../../components/tasks/TasksView.tsx";
import { ProjectsView } from "../../components/projects/ProjectsView.tsx";
import { FinanceView } from "../../components/finance/FinanceView.tsx";
import { ProductionView } from "../../components/production/ProductionView.tsx";
import { ReportingView } from "../../components/reporting/ReportingView.tsx";
import { AutomationView } from "../../components/automation/AutomationView.tsx";
import { Spinner } from "../../components/forms/Controls.tsx";
import { Icon } from "../../components/ui/Icon.tsx";
import { ModuleIcon } from "../../components/workspace/ModuleIcon.tsx";
import { ApiRequestError } from "../../lib/http.ts";
import { fetchModule, moduleForPath, readOnly, type WorkspaceModule } from "../../lib/modules.ts";

type State = { status: "loading" } | { status: "ready"; module: WorkspaceModule } | { status: "closed" | "missing" | "failed"; message: string };

export function ModulePage() {
  const { modulePath } = useParams();
  const key = moduleForPath(modulePath);
  const [state, setState] = useState<State>({ status: "loading" });
  const [loadedPath, setLoadedPath] = useState(modulePath);

  if (loadedPath !== modulePath) {
    setLoadedPath(modulePath);
    setState({ status: "loading" });
  }

  useEffect(() => {
    if (!key) {
      return;
    }
    let cancelled = false;
    fetchModule(key)
      .then((module) => {
        if (!cancelled) setState({ status: "ready", module });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (error instanceof ApiRequestError && error.status === 403) setState({ status: "closed", message: error.message });
        else if (error instanceof ApiRequestError && error.status === 404) setState({ status: "missing", message: error.message });
        else setState({ status: "failed", message: "Modül bilgisi alınamadı." });
      });
    return () => {
      cancelled = true;
    };
  }, [key]);

  if (!key) {
    return <Notice icon="info" title="Sayfa bulunamadı." body="Bu adreste bir modül yok." action={<Link to="/panel" className="font-semibold text-violet hover:underline">Ana sayfaya dön</Link>} />;
  }
  if (state.status === "loading") {
    return (
      <p role="status" className="flex items-center gap-2.5 py-16 text-[14px] text-slate">
        <Spinner className="h-4 w-4 text-violet" /> Modül yükleniyor.
      </p>
    );
  }
  if (state.status !== "ready") {
    return (
      <Notice
        icon={state.status === "closed" ? "lock" : "alert"}
        title={state.status === "closed" ? "Bu modüle erişiminiz yok." : "Modül açılamadı."}
        body={state.message}
        action={
          state.status === "closed" && !state.message.includes("yetki") ? (
            <Link to="/panel/profil#moduller" className="inline-flex h-10 items-center rounded-lg bg-graphite px-4 text-[14px] font-semibold text-onink hover:bg-midnight">
              Modül tercihlerine git
            </Link>
          ) : (
            <Link to="/panel" className="font-semibold text-violet hover:underline">
              Ana sayfaya dön
            </Link>
          )
        }
      />
    );
  }

  const { module } = state;
  const view = <ModuleView module={module} />;
  if (!readOnly(module)) return view;
  return (
    <div className="space-y-4">
      <p role="note" className="flex items-center gap-2.5 rounded-xl border border-mist/80 bg-surface px-4 py-2.5 text-[13px] text-slate">
        <Icon name="lock" className="h-4 w-4 shrink-0" />
        Bu modülü yalnızca görüntüleyebilirsiniz. Kayıt eklemek veya değiştirmek için çalışma alanı yöneticinizden düzenleme yetkisi isteyin.
      </p>
      {view}
    </div>
  );
}

function ModuleView({ module }: { module: WorkspaceModule }) {
  if (module.key === "customers") {
    return <CustomersModule module={module} />;
  }
  if (module.key === "inventory") {
    return <InventoryView module={module} />;
  }
  if (module.key === "sales") {
    return <SalesView module={module} />;
  }
  if (module.key === "tasks") {
    return <TasksView module={module} />;
  }
  if (module.key === "projects") {
    return <ProjectsView module={module} />;
  }
  if (module.key === "finance") {
    return <FinanceView module={module} />;
  }
  if (module.key === "production") {
    return <ProductionView module={module} />;
  }
  if (module.key === "reporting") {
    return <ReportingView module={module} />;
  }
  if (module.key === "automation") {
    return <AutomationView module={module} />;
  }
  return (
    <div className="space-y-8">
      <section className="flex flex-wrap items-center gap-4">
        <div className="min-w-0">
          <h1 className="font-display text-[22px] font-semibold tracking-[-0.02em] text-midnight sm:text-[24px]">{module.name}</h1>
          <p className="mt-0.5 text-[14px] text-slate">{module.summary}</p>
        </div>
      </section>

      <section className="rounded-2xl border border-mist/80 bg-surface px-6 py-14 text-center">
        <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-cloud text-slate ring-1 ring-inset ring-mist/70">
          <ModuleIcon name={module.key} className="h-6 w-6" />
        </span>
        <h2 className="mt-5 text-[16px] font-semibold">Bu modülde henüz kayıt yok.</h2>
        <p className="mx-auto mt-2 max-w-md text-[14px] leading-6 text-slate">
          {module.name} çalışma alanınızda açık ve erişiminiz sunucuda doğrulandı. Kayıt ekleme ve listeleme ekranları sıradaki geliştirme adımında bu alana gelecek.
        </p>
      </section>
    </div>
  );
}

function Notice({ icon, title, body, action }: { icon: "info" | "lock" | "alert"; title: string; body: string; action: ReactNode }) {
  return (
    <section className="mx-auto max-w-lg py-16 text-center">
      <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-surface text-slate ring-1 ring-inset ring-mist">
        <Icon name={icon} className="h-6 w-6" />
      </span>
      <h1 className="mt-5 font-display text-[22px] font-semibold tracking-tight">{title}</h1>
      <p className="mt-2 text-[14px] leading-6 text-slate">{body}</p>
      <div className="mt-6 text-[14px]">{action}</div>
    </section>
  );
}
