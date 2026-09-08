/**
 * Sessão no BFF: tokens ficam em cookies httpOnly, nunca acessíveis ao JavaScript do navegador.
 * O backend FastAPI é chamado apenas do servidor Next.js (API_URL não é pública).
 */
import { NextResponse } from "next/server";

export const ACCESS_COOKIE = "sa_access";
export const REFRESH_COOKIE = "sa_refresh";

export const API_URL = (process.env.API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const COOKIE_SECURE = process.env.COOKIE_SECURE === "true" || process.env.NODE_ENV === "production";

export type TokenPair = { accessToken: string; refreshToken: string; expiresIn: number };

const base = { httpOnly: true, sameSite: "lax" as const, secure: COOKIE_SECURE, path: "/" };

export function setSessionCookies(res: NextResponse, tokens: TokenPair) {
  res.cookies.set(ACCESS_COOKIE, tokens.accessToken, { ...base, maxAge: Math.max(60, tokens.expiresIn) });
  res.cookies.set(REFRESH_COOKIE, tokens.refreshToken, { ...base, maxAge: 60 * 60 * 24 * 30 });
}

export function clearSessionCookies(res: NextResponse) {
  res.cookies.set(ACCESS_COOKIE, "", { ...base, maxAge: 0 });
  res.cookies.set(REFRESH_COOKIE, "", { ...base, maxAge: 0 });
}

export async function refreshWithBackend(refreshToken: string, userAgent: string | null): Promise<TokenPair | null> {
  try {
    const res = await fetch(`${API_URL}/api/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...(userAgent ? { "User-Agent": userAgent } : {}) },
      body: JSON.stringify({ refreshToken }),
      cache: "no-store",
    });
    if (!res.ok) return null;
    const data = (await res.json()) as TokenPair;
    if (!data.accessToken || !data.refreshToken) return null;
    return data;
  } catch {
    return null;
  }
}
