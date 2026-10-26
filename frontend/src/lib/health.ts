export type HealthResponse = {
  status: "ok" | "degraded";
  service: string;
  environment: string;
  version: string;
  checks: {
    database: "ok" | "unavailable";
  };
};

export type HealthState =
  | { phase: "loading" }
  | { phase: "ok"; health: HealthResponse }
  | { phase: "degraded"; health: HealthResponse }
  | { phase: "unreachable" };

function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const record = value as Record<string, unknown>;
  const checks = record.checks;
  if (typeof checks !== "object" || checks === null) {
    return false;
  }

  const database = (checks as Record<string, unknown>).database;
  return (
    (record.status === "ok" || record.status === "degraded") &&
    typeof record.service === "string" &&
    typeof record.environment === "string" &&
    typeof record.version === "string" &&
    (database === "ok" || database === "unavailable")
  );
}

export async function fetchHealth(signal: AbortSignal): Promise<HealthState> {
  try {
    const response = await fetch("/api/v1/health", {
      signal,
      headers: { Accept: "application/json" },
    });
    const payload: unknown = await response.json();
    if (!isHealthResponse(payload)) {
      return { phase: "unreachable" };
    }
    if (response.status === 200 && payload.status === "ok") {
      return { phase: "ok", health: payload };
    }
    if (response.status === 503 && payload.status === "degraded") {
      return { phase: "degraded", health: payload };
    }
    return { phase: "unreachable" };
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    return { phase: "unreachable" };
  }
}
