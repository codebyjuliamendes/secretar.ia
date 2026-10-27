/**
 * Destino pós-login vindo de `?next=`: só caminhos da própria origem (evita open redirect).
 * `new URL` resolve truques como "/\\evil.com" (a barra invertida vira "/") e "//evil.com".
 */
export function safeNext(value: string | null, origin: string): string {
  if (!value || !value.startsWith("/")) return "/app";
  try {
    const url = new URL(value, origin);
    if (url.origin !== origin) return "/app";
    return url.pathname + url.search;
  } catch {
    return "/app";
  }
}
