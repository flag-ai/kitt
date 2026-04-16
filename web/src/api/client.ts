// Thin fetch wrapper that injects the admin bearer token and parses JSON.
//
// In production the SPA is served from the KITT server itself so relative
// paths resolve. In dev (vite dev server) the proxy in vite.config.ts
// forwards /api, /health, /ready to http://localhost:8080.
//
// The admin token is read from sessionStorage (set once via the Settings
// page). Storing it in sessionStorage scopes it to the browser tab so
// closing the tab clears the credential; localStorage would persist it
// across sessions which is a worse default.

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: string
  ) {
    super(`API error ${status}: ${body}`);
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = sessionStorage.getItem("kitt_admin_token") ?? "";
  const resp = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token && path.startsWith("/api/") ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (!resp.ok) {
    throw new ApiError(resp.status, await resp.text());
  }
  const ct = resp.headers.get("Content-Type") ?? "";
  if (ct.includes("application/json")) {
    return (await resp.json()) as T;
  }
  // Endpoints that return 204 / empty bodies (DELETE, 202).
  return undefined as T;
}
