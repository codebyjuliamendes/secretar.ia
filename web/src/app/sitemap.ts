import type { MetadataRoute } from "next";
import { NICHE_PAGES } from "@/lib/niche-pages";

const BASE = (process.env.PUBLIC_WEB_URL ?? "http://localhost:4000").replace(/\/$/, "");

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return [
    { url: `${BASE}/`, lastModified: now, priority: 1 },
    ...NICHE_PAGES.map((n) => ({ url: `${BASE}/para/${n.slug}`, lastModified: now, priority: 0.8 })),
  ];
}
