import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "TaxiAI",
  description: "AI-копилот для водителя такси — спрос, прогноз, финансы",
  manifest: "/manifest.json",
};

export const viewport: Viewport = {
  themeColor: "#0d0d0d",
};

const NAV_ITEMS = [
  { href: "/", label: "Карта" },
  { href: "/trips", label: "Поездки" },
  { href: "/finance", label: "Финансы" },
  { href: "/chat", label: "AI-чат" },
];

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ru"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <header className="border-b border-white/10 bg-[var(--surface-1)]">
          <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
            <span className="font-semibold tracking-tight">TaxiAI</span>
            <nav className="flex gap-4 text-sm">
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
                >
                  {item.label}
                </Link>
              ))}
              <Link href="/onboarding" className="text-[var(--series-1)]">
                Настройки
              </Link>
            </nav>
          </div>
        </header>
        <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
