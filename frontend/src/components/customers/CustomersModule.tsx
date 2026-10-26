import { useSearchParams } from "react-router";
import type { WorkspaceModule } from "../../lib/modules.ts";
import { QuotesView } from "../quotes/QuotesView.tsx";
import { CustomersView } from "./CustomersView.tsx";

const sections = [
  { value: "musteriler", label: "Müşteriler" },
  { value: "teklifler", label: "Teklifler" },
] as const;

export function CustomersModule({ module }: { module: WorkspaceModule }) {
  const [params, setParams] = useSearchParams();
  const section = params.get("bolum") === "teklifler" ? "teklifler" : "musteriler";
  const switcher = (
    <nav aria-label="Bölüm" className="flex gap-1 border-b border-mist">
      {sections.map((item) => (
        <button
          key={item.value}
          type="button"
          aria-current={section === item.value ? "page" : undefined}
          onClick={() => setParams(item.value === "teklifler" ? { bolum: "teklifler" } : {}, { replace: true })}
          className={`-mb-px h-10 border-b-2 px-3 text-[14px] font-semibold transition-colors ${
            section === item.value ? "border-violet text-graphite" : "border-transparent text-slate hover:text-graphite"
          }`}
        >
          {item.label}
        </button>
      ))}
    </nav>
  );
  return section === "teklifler" ? <QuotesView module={module} switcher={switcher} /> : <CustomersView module={module} switcher={switcher} />;
}
