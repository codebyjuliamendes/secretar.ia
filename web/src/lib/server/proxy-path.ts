/**
 * Caminho repassado pelo BFF ao backend. Os segmentos do catch-all chegam DECODIFICADOS ("%2e%2e" vira "..",
 * "%2f" vira "/"); sem validar, `clinic/../webhooks/...` driblaria o bloqueio de rotas internas depois que o
 * fetch normalizasse a URL.
 */
const BLOCKED_PREFIXES = ["webhooks/", "internal/"];
const BLOCKED_EXACT = new Set(["integrations/google/notify"]);

export function isSafeSegment(segment: string): boolean {
  return segment !== "" && segment !== "." && segment !== ".." && !segment.includes("/") && !segment.includes("\\");
}

export type ProxyPath = { ok: true; path: string; encoded: string } | { ok: false; status: 400 | 404 };

export function resolveProxyPath(segments: string[]): ProxyPath {
  if (!segments.length || !segments.every(isSafeSegment)) return { ok: false, status: 400 };
  const path = segments.join("/");
  if (BLOCKED_PREFIXES.some((p) => path.startsWith(p)) || BLOCKED_EXACT.has(path)) return { ok: false, status: 404 };
  return { ok: true, path, encoded: segments.map(encodeURIComponent).join("/") };
}
