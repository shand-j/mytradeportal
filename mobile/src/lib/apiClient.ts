import { config } from "./config";
import { camelizeKeys, snakeizeKeys } from "./case";
import { tokenStorage } from "./tokenStorage";
import { usePaywallStore } from "../stores/paywallStore";

export class ApiError extends Error {
  status: number;
  detail: string;
  /** Machine-readable code when the server sends structured detail
   * (e.g. dispatch guardrail rejections: schedule_conflict, daily_hours_cap,
   * job_locked). Null for plain-string details. */
  code: string | null;
  constructor(status: number, detail: string, code: string | null = null) {
    super(detail || `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.code = code;
  }
}

/** Thrown when the backend is unreachable (offline / no signal / no server). */
export class NetworkError extends Error {
  constructor(message = "Network unavailable") {
    super(message);
    this.name = "NetworkError";
  }
}

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  /** camelCase body; converted to snake_case on the wire. */
  body?: unknown;
  /** Skip attaching the Authorization/X-Tenant-ID headers (e.g. public config). */
  auth?: boolean;
  /** Extra headers to merge in (e.g. X-Setup-Token for tenant bootstrap). */
  headers?: Record<string, string>;
  signal?: AbortSignal;
  /** Per-request timeout override (AI generation calls need minutes). */
  timeoutMs?: number;
};

/** Requests abort after this long so a hung server shows the offline/retry UI. */
const DEFAULT_TIMEOUT_MS = 60_000;

/** LLM-backed calls (quote generation/refine, AI chat follow-up) can take
 * 60–120s with the current model; they must not hit the default timeout. */
export const AI_TIMEOUT_MS = 240_000;

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  if (!config.apiBaseUrl) {
    throw new NetworkError("No API base URL configured");
  }

  const { method = "GET", body, auth = true, headers: extraHeaders, signal } = options;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const headers: Record<string, string> = { Accept: "application/json" };

  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  if (auth) {
    const [token, tenantId] = await Promise.all([
      tokenStorage.getToken(),
      tokenStorage.getTenantId(),
    ]);
    if (token) headers["Authorization"] = `Bearer ${token}`;
    if (tenantId) headers["X-Tenant-ID"] = tenantId;
  }

  if (extraHeaders) {
    Object.assign(headers, extraHeaders);
  }

  const timeoutController = new AbortController();
  let timedOut = false;
  const timeoutId = setTimeout(() => {
    timedOut = true;
    timeoutController.abort();
  }, timeoutMs);

  // Aborted by the caller's signal too, if one was provided.
  const onCallerAbort = () => timeoutController.abort();
  if (signal) {
    if (signal.aborted) {
      clearTimeout(timeoutId);
      throw new NetworkError();
    }
    signal.addEventListener("abort", onCallerAbort);
  }

  let response: Response;
  try {
    response = await fetch(`${config.apiBaseUrl}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(snakeizeKeys(body)) : undefined,
      signal: timeoutController.signal,
    });
  } catch {
    // fetch only rejects on network failure or abort (not on HTTP error codes).
    if (timedOut) {
      throw new NetworkError(`Request timed out after ${timeoutMs / 1000}s`);
    }
    throw new NetworkError();
  } finally {
    clearTimeout(timeoutId);
    if (signal) signal.removeEventListener("abort", onCallerAbort);
  }

  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      // Non-JSON error bodies (e.g. an edge proxy's HTML 500 page) must not
      // crash the caller with a JSON parse error — treat as no payload.
      payload = null;
    }
  }

  if (!response.ok) {
    // FastAPI error bodies are {detail: ...}. Detail is usually a string, but
    // structured rejections (e.g. dispatch guardrail 409s) send an object —
    // {code, reason} — and validation 422s send an array of {msg} objects.
    // Flatten all three so callers always get a toastable message, and keep
    // the machine-readable code for clients that want to branch on it.
    let detail = response.statusText;
    let code: string | null = null;
    const raw = payload && typeof payload === "object" ? (payload as { detail?: unknown }).detail : undefined;
    if (typeof raw === "string") {
      detail = raw;
    } else if (Array.isArray(raw)) {
      detail = raw
        .map((item) =>
          item && typeof item === "object" && "msg" in item ? String(item.msg) : String(item)
        )
        .join("; ");
    } else if (raw && typeof raw === "object") {
      const structured = raw as { code?: unknown; reason?: unknown };
      code = typeof structured.code === "string" ? structured.code : null;
      detail =
        typeof structured.reason === "string"
          ? structured.reason
          : (code ?? JSON.stringify(raw));
    }
    // 402 subscription_required: flag globally so the app routes staff to the
    // paywall. The billing endpoints themselves are exempt server-side, so
    // this only fires for genuinely gated data endpoints.
    if (response.status === 402) {
      usePaywallStore.getState().setRequired(true);
    }
    throw new ApiError(response.status, detail, code);
  }

  return camelizeKeys(payload) as T;
}

export const api = {
  get: <T>(path: string, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method">) =>
    request<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "method">) =>
    request<T>(path, { ...options, method: "PATCH", body }),
  delete: <T>(path: string, options?: Omit<RequestOptions, "method" | "body">) =>
    request<T>(path, { ...options, method: "DELETE" }),
};
