import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BiRef Studio — Arka planın ötesinde",
  description: "Yerel yapay zekâ ile fotoğraflarınızın arka planını kaldırın, düzenleyin ve indirin.",
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="tr"><body>{children}</body></html>;
}
