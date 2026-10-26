import type { ModuleKey } from "../../lib/modules.ts";

const paths: Record<ModuleKey, string[]> = {
  sales: ["M6 8h12l-1 12H7L6 8Z", "M9 8V6.5a3 3 0 0 1 6 0V8", "M9.5 12.5h5"],
  inventory: ["M12 3 20 7.5v9L12 21l-8-4.5v-9L12 3Z", "M4 7.5 12 12l8-4.5", "M12 12v9"],
  production: ["M3.5 20V10l5 3v-3l5 3V6h3v14h-13Z", "M3 20h18", "M7 17h2", "M11 17h2"],
  customers: [
    "M9 11.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4Z",
    "M3.5 19c.8-3 3-4.6 5.5-4.6s4.7 1.6 5.5 4.6",
    "M15.5 5.2a3 3 0 0 1 0 5.6",
    "M17.5 14.6c1.6.6 2.6 2 3 4.4",
  ],
  finance: ["M4 7h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7Z", "M4 7l11-3v3", "M16 13h.01"],
  tasks: ["M6 4h12a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z", "M8.5 9.5 10 11l3-3", "M8.5 15h7"],
  projects: ["M3.5 7.5a2 2 0 0 1 2-2H10l2 2h6.5a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2V7.5Z", "M8 13h8"],
  reporting: ["M4 4v16h16", "M8 16v-4", "M12 16V8", "M16 16v-6"],
  automation: ["M13 3 5 13.5h6L10.5 21 19 10h-6L13 3Z"],
};

export function ModuleIcon({ name, className = "h-5 w-5" }: { name: ModuleKey; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden className={className}>
      {paths[name].map((d) => (
        <path key={d} d={d} stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      ))}
    </svg>
  );
}
