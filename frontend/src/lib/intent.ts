import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";

export type IntentCustomer = { id: string; label: string };
export type IntentSource = { kind: "quote" | "order"; id: string; label: string };
export type CreateIntent = { customer: IntentCustomer | null; source: IntentSource | null };

const KEYS = ["yeni", "musteri", "musteri_adi", "kaynak", "kaynak_id", "kaynak_kod"];

export function createLink(path: string, customer: IntentCustomer, source?: IntentSource): string {
  const params = new URLSearchParams({ yeni: "1", musteri: customer.id, musteri_adi: customer.label });
  if (source) {
    params.set("kaynak", source.kind === "quote" ? "teklif" : "siparis");
    params.set("kaynak_id", source.id);
    params.set("kaynak_kod", source.label);
  }
  return `${path}${path.includes("?") ? "&" : "?"}${params}`;
}

export function useCreateIntent(): CreateIntent | null {
  const [params, setParams] = useSearchParams();
  const [intent] = useState<CreateIntent | null>(() => {
    if (params.get("yeni") !== "1") return null;
    const id = params.get("musteri");
    const label = params.get("musteri_adi");
    const kind = params.get("kaynak");
    const sourceId = params.get("kaynak_id");
    const code = params.get("kaynak_kod");
    const source: IntentSource | null =
      (kind === "teklif" || kind === "siparis") && sourceId && code ? { kind: kind === "teklif" ? "quote" : "order", id: sourceId, label: code } : null;
    return { customer: id && label ? { id, label } : null, source };
  });

  useEffect(() => {
    if (!intent) return;
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        for (const key of KEYS) next.delete(key);
        return next;
      },
      { replace: true },
    );
  }, [intent, setParams]);

  return intent;
}
