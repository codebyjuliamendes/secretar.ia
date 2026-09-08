/**
 * Proteção de rotas no edge: sem cookie de sessão, áreas autenticadas redirecionam para /login.
 * A autorização real (tenant/papel) é sempre validada no backend; aqui só evitamos telas vazias.
 */
import { NextRequest, NextResponse } from "next/server";

const REFRESH_COOKIE = "sa_refresh";
const PROTECTED = ["/app", "/admin", "/account"];
const PUBLIC_ONLY = ["/login", "/register"];

export default function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const hasSession = Boolean(req.cookies.get(REFRESH_COOKIE)?.value);

  if (PROTECTED.some((p) => pathname === p || pathname.startsWith(`${p}/`)) && !hasSession) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  if (PUBLIC_ONLY.includes(pathname) && hasSession) {
    const url = req.nextUrl.clone();
    url.pathname = "/app";
    url.search = "";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/app/:path*", "/admin/:path*", "/account/:path*", "/login", "/register"],
};
