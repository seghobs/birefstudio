import type { Metadata } from "next";
import "./globals.css";
import "./studio.css";

export const metadata: Metadata = {
  title: "BiRef Studio — Fotoğraf & Baskı Masası",
  description: "Yerel yapay zekâ ile fotoğraflarınızın arka planını kaldırın, düzenleyin ve indirin.",
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="tr"><body>{children}</body></html>;
}
