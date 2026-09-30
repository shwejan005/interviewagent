/**
 * Typed fetch wrapper for the Evalia API.
 *
 * Two pieces of request state live outside React (localStorage), because
 * they need to survive a full page reload without a flash of "logged out":
 * the bearer token and the active organization ID (sent as `X-Org-Id`, which
 * lets a user who belongs to several orgs switch context without
 * re-authenticating — see docs/API_REFERENCE.md).
 */

const API_BASE = "/api";

const TOKEN_KEY = "evalia_token";
const TOKEN_EXPIRES_AT_KEY = "evalia_token_expires_at";
const ORG_KEY = "evalia_org_id";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

function decodeTokenExpiry(token: string): number | null {
  if (typeof window === "undefined") return null;

  const encodedPayload = token.split(".")[1];
  if (!encodedPayload) return null;

  try {
    const normalizedPayload = encodedPayload.replace(/-/g, "+").replace(/_/g, "/");
    const paddedPayload = normalizedPayload.padEnd(Math.ceil(normalizedPayload.length / 4) * 4, "=");
    const payload = JSON.parse(window.atob(paddedPayload)) as { exp?: unknown };
    return typeof payload.exp === "number" && Number.isFinite(payload.exp) ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

export function getTokenExpiresAt(): number | null {
  if (typeof window === "undefined") return null;

  const storedExpiry = Number(window.localStorage.getItem(TOKEN_EXPIRES_AT_KEY));
  if (Number.isFinite(storedExpiry) && storedExpiry > 0) return storedExpiry;

  const token = getToken();
  const decodedExpiry = token ? decodeTokenExpiry(token) : null;
  if (decodedExpiry) window.localStorage.setItem(TOKEN_EXPIRES_AT_KEY, String(decodedExpiry));
  return decodedExpiry;
}

export function setToken(token: string, expiresIn?: number): void {
  window.localStorage.setItem(TOKEN_KEY, token);
  const expiresAt =
    typeof expiresIn === "number" && Number.isFinite(expiresIn)
      ? Date.now() + Math.max(0, expiresIn) * 1000
      : decodeTokenExpiry(token);

  if (expiresAt) {
    window.localStorage.setItem(TOKEN_EXPIRES_AT_KEY, String(expiresAt));
  } else {
    window.localStorage.removeItem(TOKEN_EXPIRES_AT_KEY);
  }
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(TOKEN_EXPIRES_AT_KEY);
}

export function getActiveOrgId(): number | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(ORG_KEY);
  return raw ? Number(raw) : null;
}

export function setActiveOrgId(orgId: number | null): void {
  if (orgId === null) {
    window.localStorage.removeItem(ORG_KEY);
  } else {
    window.localStorage.setItem(ORG_KEY, String(orgId));
  }
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

function formatApiDetail(detail: unknown): string | null {
  if (typeof detail === "string" && detail.trim()) return detail;

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (!item || typeof item !== "object") return String(item);
        const issue = item as { loc?: unknown; msg?: unknown };
        const location = Array.isArray(issue.loc)
          ? issue.loc
              .filter((part): part is string | number => typeof part === "string" || typeof part === "number")
              .slice(1)
              .join(".")
          : "";
        const message = typeof issue.msg === "string" ? issue.msg : "Invalid value";
        return location ? `${location}: ${message}` : message;
      })
      .filter(Boolean);
    if (messages.length) return messages.join("; ");
  }

  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
  }

  return null;
}

type FetchOptions = {
  method?: string;
  body?: unknown;
  /** Override the active org header for this call only (rarely needed). */
  orgId?: number | null;
  /** Skip attaching the bearer token, for public endpoints called while logged out. */
  skipAuth?: boolean;
};

export async function apiFetch<T = unknown>(path: string, options: FetchOptions = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };

  if (!options.skipAuth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const orgId = options.orgId !== undefined ? options.orgId : getActiveOrgId();
  if (orgId !== null) headers["X-Org-Id"] = String(orgId);

  const res = await fetch(`${API_BASE}${path}`, {
    method: options.method || (options.body ? "POST" : "GET"),
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  if (res.status === 204) return undefined as T;

  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    // A non-JSON body (e.g. a proxy error page) still needs a legible message.
  }

  if (!res.ok) {
    const detail =
      (data && typeof data === "object" && "detail" in data
        ? formatApiDetail((data as { detail: unknown }).detail)
        : null) ||
      (res.status === 429
        ? "Too many requests. Please slow down and try again shortly."
        : `Request failed (${res.status}).`);
    throw new ApiError(res.status, detail);
  }

  return data as T;
}

export async function apiUpload<T = unknown>(path: string, file: File, options: Pick<FetchOptions, "orgId" | "skipAuth"> = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (!options.skipAuth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const orgId = options.orgId !== undefined ? options.orgId : getActiveOrgId();
  if (orgId !== null) headers["X-Org-Id"] = String(orgId);

  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}${path}`, { method: "POST", headers, body: form });

  if (res.status === 204) return undefined as T;
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    // Preserve the same normalized error behavior as JSON requests.
  }
  if (!res.ok) {
    const detail =
      (data && typeof data === "object" && "detail" in data
        ? formatApiDetail((data as { detail: unknown }).detail)
        : null) || `Request failed (${res.status}).`;
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

export const api = {
  get: <T = unknown>(path: string, options?: FetchOptions) =>
    apiFetch<T>(path, { ...options, method: "GET" }),
  post: <T = unknown>(path: string, body?: unknown, options?: FetchOptions) =>
    apiFetch<T>(path, { ...options, method: "POST", body: body ?? {} }),
  put: <T = unknown>(path: string, body?: unknown, options?: FetchOptions) =>
    apiFetch<T>(path, { ...options, method: "PUT", body: body ?? {} }),
  patch: <T = unknown>(path: string, body?: unknown, options?: FetchOptions) =>
    apiFetch<T>(path, { ...options, method: "PATCH", body: body ?? {} }),
  delete: <T = unknown>(path: string, options?: FetchOptions) =>
    apiFetch<T>(path, { ...options, method: "DELETE" }),
  upload: <T = unknown>(path: string, file: File, options?: Pick<FetchOptions, "orgId" | "skipAuth">) =>
    apiUpload<T>(path, file, options),
};
