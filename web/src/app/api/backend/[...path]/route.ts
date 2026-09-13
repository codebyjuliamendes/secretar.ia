/**
 * BFF: encaminha /api/backend/* para o FastAPI anexando o access token do cookie httpOnly.
 * - Em 401 com refresh token disponível, renova a sessão uma vez e repete a chamada.
 * - Respostas de login/registro/refresh têm os tokens movidos para cookies (nunca chegam ao JS).
 * - Logout revoga no backend e limpa cookies.
 */
import { NextRequest, NextResponse } from "next/server";
import {
  ACCESS_COOKIE,
  API_URL,
  REFRESH_COOKIE,
  clearSessionCookies,
  refreshWithBackend,
  setSessionCookies,
  type TokenPair,
} from "@/lib/server/session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const AUTH_TOKEN_PATHS = new Set(["auth/login", "auth/register", "auth/refresh"]);
const FORWARD_HEADERS = ["content-type", "accept", "user-agent", "x-request-id"];
const MUTATING = new Set(["POST", "PATCH", "PUT", "DELETE"]);

/**
 * Renovações em voo por refresh token: N chamadas paralelas com o access vencido compartilham UMA renovação.
 * Sem isso, a segunda rotação encontraria o token já revogado e o backend trataria como reuso (roubo).
 */
const inflightRefresh = new Map<string, Promise<TokenPair | null>>();
function refreshOnce(refreshToken: string, userAgent: string | null) {
  const existing = inflightRefresh.get(refreshToken);
  if (existing) return existing;
  const p = refreshWithBackend(refreshToken, userAgent).finally(() => {
    // pequena janela para requisições que ainda estão chegando com o mesmo cookie antigo
    setTimeout(() => inflightRefresh.delete(refreshToken), 5000);
  });
  inflightRefresh.set(refreshToken, p);
  return p;
}

/** IP do visitante como o proxy da plataforma o entrega (x-real-ip ou o último salto de x-forwarded-for). */
function clientIp(req: NextRequest) {
  const real = req.headers.get("x-real-ip");
  if (real) return real.trim();
  const fwd = req.headers.get("x-forwarded-for");
  if (!fwd) return null;
  const parts = fwd.split(",").map((s) => s.trim()).filter(Boolean);
  return parts.length ? parts[parts.length - 1] : null;
}

/** CSRF em profundidade: além de SameSite=Lax, requisições que alteram estado precisam vir da própria origem. */
function crossOrigin(req: NextRequest) {
  if (!MUTATING.has(req.method)) return false;
  const origin = req.headers.get("origin");
  if (!origin) return false; // navegadores mandam Origin em POST/PATCH/DELETE; sem ele, é cliente não-navegador
  try {
    return new URL(origin).host !== req.nextUrl.host;
  } catch {
    return true;
  }
}

type Ctx = { params: Promise<{ path: string[] }> };

async function forward(req: NextRequest, path: string, accessToken: string | undefined, body: ArrayBuffer | null) {
  const headers = new Headers();
  for (const h of FORWARD_HEADERS) {
    const v = req.headers.get(h);
    if (v) headers.set(h, v);
  }
  const ip = clientIp(req);
  if (ip) {
    headers.set("x-forwarded-for", ip);
    headers.set("x-real-ip", ip);
  }
  if (accessToken) headers.set("authorization", `Bearer ${accessToken}`);
  const url = `${API_URL}/api/${path}${req.nextUrl.search}`;
  const init: RequestInit = { method: req.method, headers, cache: "no-store", redirect: "manual" };
  if (body && body.byteLength > 0 && req.method !== "GET" && req.method !== "HEAD") init.body = body;
  return fetch(url, init);
}

function errorResponse(status: number, code: string, message: string) {
  return NextResponse.json({ error: { code, message } }, { status });
}

async function handle(req: NextRequest, ctx: Ctx) {
  const { path: segments } = await ctx.params;
  const path = segments.join("/");
  if (path.startsWith("webhooks/") || path.startsWith("internal/") || path === "integrations/google/notify") {
    return errorResponse(404, "not_found", "Rota indisponível.");
  }
  if (crossOrigin(req)) {
    return errorResponse(403, "cross_origin", "Requisição de outra origem recusada.");
  }
  const body = req.method === "GET" || req.method === "HEAD" ? null : await req.arrayBuffer();
  let accessToken = req.cookies.get(ACCESS_COOKIE)?.value;
  const refreshToken = req.cookies.get(REFRESH_COOKIE)?.value;
  let renewed: TokenPair | null = null;

  if (path === "auth/logout") {
    const payload = refreshToken ? JSON.stringify({ refreshToken }) : "{}";
    try {
      await fetch(`${API_URL}/api/auth/logout`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(accessToken ? { authorization: `Bearer ${accessToken}` } : {}) },
        body: payload,
        cache: "no-store",
      });
    } catch {
      // cookies são limpos de qualquer forma
    }
    const res = new NextResponse(null, { status: 204 });
    clearSessionCookies(res);
    return res;
  }

  let upstream: Response;
  try {
    upstream = await forward(req, path, accessToken, body);
    if (upstream.status === 401 && refreshToken && !AUTH_TOKEN_PATHS.has(path)) {
      renewed = await refreshOnce(refreshToken, req.headers.get("user-agent"));
      if (renewed) {
        accessToken = renewed.accessToken;
        upstream = await forward(req, path, accessToken, body);
      }
    }
  } catch {
    return errorResponse(503, "backend_unavailable", "Serviço temporariamente indisponível. Tente novamente.");
  }

  const contentType = upstream.headers.get("content-type") ?? "";
  let res: NextResponse;
  if (AUTH_TOKEN_PATHS.has(path) && upstream.ok && contentType.includes("application/json")) {
    const data = (await upstream.json()) as TokenPair & Record<string, unknown>;
    const { accessToken: at, refreshToken: rt, expiresIn, ...rest } = data;
    res = NextResponse.json(rest, { status: upstream.status });
    setSessionCookies(res, { accessToken: at, refreshToken: rt, expiresIn });
    return res;
  }

  if (upstream.status === 204) {
    res = new NextResponse(null, { status: 204 });
  } else {
    const buf = await upstream.arrayBuffer();
    res = new NextResponse(buf, { status: upstream.status, headers: { "content-type": contentType || "application/json" } });
  }
  const rid = upstream.headers.get("x-request-id");
  if (rid) res.headers.set("x-request-id", rid);
  if (renewed) setSessionCookies(res, renewed);
  if (upstream.status === 401 && !AUTH_TOKEN_PATHS.has(path)) clearSessionCookies(res);
  return res;
}

export { handle as GET, handle as POST, handle as PATCH, handle as PUT, handle as DELETE };
