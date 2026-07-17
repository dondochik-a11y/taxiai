import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { DesktopNav, MobileTabBar } from "@/components/Nav";
import { ServiceWorkerRegister } from "@/components/ServiceWorkerRegister";

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
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
  },
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
        <header className="sticky top-0 z-40 border-b border-white/10 bg-[rgba(13,13,13,0.92)] backdrop-blur pt-[env(safe-area-inset-top)]">
          <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
              <span className="w-7 h-7 rounded-lg bg-[var(--series-1)] flex items-center justify-center text-white">
                <svg
                  viewBox="0 0 24 24"
                  className="w-4 h-4"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M5 11.5 6.4 7A2 2 0 0 1 8.3 5.6h7.4A2 2 0 0 1 17.6 7L19 11.5" />
                  <path d="M3.5 11.5h17v4.4a1 1 0 0 1-1 1h-1.3a1 1 0 0 1-1-1v-.9H6.8v.9a1 1 0 0 1-1 1H4.5a1 1 0 0 1-1-1v-4.4Z" />
                  <path d="M6.7 14h.01M17.3 14h.01" />
                </svg>
              </span>
              TaxiAI
            </Link>
            <DesktopNav />
          </div>
        </header>
        <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-4 md:py-6 pb-[calc(6.5rem+env(safe-area-inset-bottom))] md:pb-6">
          {children}
        </main>
        <MobileTabBar />
        <ServiceWorkerRegister />
      </body>
    </html>
  );
}
