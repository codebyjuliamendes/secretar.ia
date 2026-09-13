import type { PublicConfig } from "@/lib/types";
import { API_URL } from "./session";

/** Planos, nichos e contato comercial para páginas públicas. Null se o backend estiver fora: a landing continua de pé. */
export async function getPublicConfig(): Promise<PublicConfig | null> {
  try {
    const res = await fetch(`${API_URL}/api/public/config`, { next: { revalidate: 300 } });
    if (!res.ok) return null;
    return (await res.json()) as PublicConfig;
  } catch {
    return null;
  }
}
