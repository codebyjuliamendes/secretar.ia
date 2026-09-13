/** Cliente HTTP do navegador. Fala apenas com o BFF (/api/backend) — nunca com o FastAPI direto. */

export class ApiError extends Error {
  status: number;
  code: string;
  details?: { field: string; message: string }[];
  requestId?: string | null;

  constructor(status: number, code: string, message: string, details?: ApiError["details"], requestId?: string | null) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

function qs(query?: Query) {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  let res: Response;
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  try {
    res = await fetch(`/api/backend/${path.replace(/^\//, "")}${qs(query)}`, {
      method,
      // FormData: o navegador define o Content-Type multipart com o boundary.
      headers: body !== undefined && !isForm ? { "Content-Type": "application/json" } : undefined,
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "network_error", "Sem conexão. Verifique sua internet e tente novamente.");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string; details?: ApiError["details"]; request_id?: string } })
      ?.error;
    if (res.status === 401) {
      // Sessão expirada/revogada: força novo login preservando o destino.
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}&expired=1`);
      }
    }
    throw new ApiError(
      res.status,
      err?.code ?? "http_error",
      err?.message ?? "Não foi possível concluir a operação.",
      err?.details,
      err?.request_id ?? res.headers.get("x-request-id"),
    );
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>("GET", path, undefined, query),
  post: <T>(path: string, body?: unknown, query?: Query) => request<T>("POST", path, body ?? {}, query),
  upload: <T>(path: string, form: FormData) => request<T>("POST", path, form),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  delete: <T = void>(path: string) => request<T>("DELETE", path),
};

/** Consulta silenciosa: devolve null em 401/erro, sem redirecionar para o login (ex.: "estou logado?"). */
export async function probe<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`/api/backend/${path.replace(/^\//, "")}`, { credentials: "same-origin", cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    // 422: diz qual campo falhou em vez de um "Dados inválidos" genérico.
    if (err.details?.length) return `${err.message} ${err.details.map((d) => `${d.field}: ${d.message}`).join("; ")}`;
    return err.message;
  }
  if (err instanceof Error) return err.message;
  return "Algo deu errado. Tente novamente.";
}
