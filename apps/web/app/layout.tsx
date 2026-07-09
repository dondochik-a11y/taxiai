import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { DesktopNav, MobileTabBar } from "@/components/Nav";

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
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "TaxiAI",
  },
};

export const viewport: Viewport = {
  themeColor: "#0d0d0d",
  viewportFit: "cover",
  width: "device-width",
  initialScale: 1,
};

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
        <header className="sticky top-0 z-40 border-b border-white/10 bg-[rgba(13,13,13,0.92)] backdrop-blur">
          <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
              <span className="w-7 h-7 rounded-lg bg-[var(--series-1)] flex items-center justify-center text-sm">
                🚕
              </span>
              TaxiAI
            </Link>
            <DesktopNav />
          </div>
        </header>
        <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-4 md:py-6 pb-24 md:pb-6">
          {children}
        </main>
        <MobileTabBar />
      </body>
    </html>
  );
}
