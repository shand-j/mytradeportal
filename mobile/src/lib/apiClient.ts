import { config } from "./config";
import { camelizeKeys, snakeizeKeys } from "./case";
import { tokenStorage } from "./tokenStorage";

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail || `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
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
  const payload = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : response.statusText;
    throw new ApiError(response.status, detail);
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
