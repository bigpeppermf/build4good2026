/**
 * Build API URLs. In dev (no VITE_API_URL), paths use the `/api` prefix so Vite
 * proxies to the Python server. With VITE_API_URL set, paths are rooted at that
 * origin without a duplicate `/api` segment.
 */
export function apiUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  const base = (import.meta.env.VITE_API_URL as string | undefined)?.trim();
  if (base) {
    const withoutApi = p.replace(/^\/api/, "") || "/";
    return `${base.replace(/\/$/, "")}${withoutApi}`;
  }
  if (p.startsWith("/api")) {
    return p;
  }
  return `/api${p}`;
}
