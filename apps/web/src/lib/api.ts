export const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(API + path, { ...options, headers: { "X-Factory-Client": "local", ...(options?.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...options?.headers } });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => ({}));
    const detail = typeof body === "object" && body !== null && "detail" in body ? body.detail : response.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return response.json() as Promise<T>;
}
export function send<T>(path: string, body: unknown, method = "POST") { return api<T>(path, { method, body: JSON.stringify(body) }); }
export function formatBytes(bytes: number) { return bytes < 1048576 ? `${(bytes/1024).toFixed(1)} KB` : `${(bytes/1048576).toFixed(1)} MB`; }
export function statusTone(status: string) { return /FAILED|CANCELLED|ERROR/.test(status) ? "red" : /APPROVED|PUBLISHED|READY$/.test(status) ? "green" : /WAITING|REVIEW|PAUSED|AUTH|MISSING|UNAVAILABLE/.test(status) ? "amber" : "blue"; }
