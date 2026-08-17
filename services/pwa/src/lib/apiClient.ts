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
  signal?: AbortSignal;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  if (!config.apiEnabled) {
    throw new NetworkError("No API base URL configured (demo mode)");
  }

  const { method = "GET", body, auth = true, signal } = options;
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

  let response: Response;
  try {
    response = await fetch(`${config.apiBaseUrl}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(snakeizeKeys(body)) : undefined,
      signal,
    });
  } catch {
    // fetch only rejects on network failure (not on HTTP error codes).
    throw new NetworkError();
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
