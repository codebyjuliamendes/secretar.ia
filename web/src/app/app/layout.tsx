import { SessionProvider } from "@/components/session";

export default function AppRootLayout({ children }: { children: React.ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>;
}
