import { ApiRequestError, getJson, isRecord, postJson, sendJson } from "./http.ts";

export type ModuleKey =
  | "sales"
  | "inventory"
  | "production"
  | "customers"
  | "finance"
  | "tasks"
  | "projects"
  | "reporting"
  | "automation";

export type WorkspaceModule = {
  key: ModuleKey;
  name: string;
  summary: string;
  requires: ModuleKey[];
  enabled: boolean;
  enabled_at: string | null;
  company_enabled?: boolean;
  access?: "view" | "edit" | null;
};

export function readOnly(module: WorkspaceModule): boolean {
  return module.access === "view";
}

export const modulePaths: Record<ModuleKey, string> = {
  sales: "satis",
  inventory: "stok",
  production: "uretim",
  customers: "musteriler",
  finance: "finans",
  tasks: "gorevler",
  projects: "projeler",
  reporting: "raporlar",
  automation: "otomasyon",
};

export const moduleShortNames: Record<ModuleKey, string> = {
  sales: "Satış",
  inventory: "Stok",
  production: "Üretim",
  customers: "Müşteriler",
  finance: "Finans",
  tasks: "Görevler",
  projects: "Projeler",
  reporting: "Raporlar",
  automation: "Otomasyon",
};

export function moduleForPath(path: string | undefined): ModuleKey | undefined {
  return (Object.keys(modulePaths) as ModuleKey[]).find((key) => modulePaths[key] === path);
}

export function withRequirements(modules: WorkspaceModule[], keys: Iterable<ModuleKey>): Set<ModuleKey> {
  const byKey = new Map(modules.map((module) => [module.key, module]));
  const selected = new Set(keys);
  const pending = [...selected];
  while (pending.length > 0) {
    const key = pending.pop();
    for (const required of key ? (byKey.get(key)?.requires ?? []) : []) {
      if (!selected.has(required)) {
        selected.add(required);
        pending.push(required);
      }
    }
  }
  return selected;
}

export function requiredBy(modules: WorkspaceModule[], chosen: Set<ModuleKey>, key: ModuleKey): WorkspaceModule[] {
  return modules.filter((module) => chosen.has(module.key) && withRequirements(modules, [module.key]).has(key) && module.key !== key);
}

export async function fetchModules(): Promise<WorkspaceModule[]> {
  return readModules(await getJson("/api/v1/modules"));
}

export async function fetchModule(key: ModuleKey): Promise<WorkspaceModule> {
  const [module] = readModules({ modules: [await getJson(`/api/v1/modules/${key}`)] });
  return module;
}

export async function completeSetup(keys: ModuleKey[]): Promise<WorkspaceModule[]> {
  return readModules(await postJson("/api/v1/workspace/setup", { modules: keys }));
}

export async function saveModules(keys: ModuleKey[]): Promise<WorkspaceModule[]> {
  return readModules(await sendJson("PUT", "/api/v1/modules", { modules: keys }));
}

function isModuleKey(value: unknown): value is ModuleKey {
  return typeof value === "string" && value in modulePaths;
}

function readModules(payload: unknown): WorkspaceModule[] {
  if (!isRecord(payload) || !Array.isArray(payload.modules)) {
    throw new ApiRequestError(500, "Modül listesi okunamadı.");
  }
  return payload.modules.map((item: unknown) => {
    if (
      !isRecord(item) ||
      !isModuleKey(item.key) ||
      typeof item.name !== "string" ||
      typeof item.summary !== "string" ||
      typeof item.enabled !== "boolean" ||
      !Array.isArray(item.requires) ||
      !item.requires.every(isModuleKey)
    ) {
      throw new ApiRequestError(500, "Modül listesi okunamadı.");
    }
    return {
      key: item.key,
      name: item.name,
      summary: item.summary,
      requires: item.requires,
      enabled: item.enabled,
      enabled_at: typeof item.enabled_at === "string" ? item.enabled_at : null,
      company_enabled: item.company_enabled === true,
      access: item.access === "view" || item.access === "edit" ? item.access : null,
    };
  });
}
