import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/layout/Sidebar";
import { ScraperProvider } from "@/components/providers/ScraperProvider";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Trend Analiz Sistemi | Akademik Araştırma",
  description: "Yapay Zeka Destekli Bilimsel Dergilerin Trend Analiz Sistemi",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="tr">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <ScraperProvider>
          <div className="flex min-h-screen">
            <Sidebar />
            <main className="ml-64 flex-1 p-8">
              {children}
            </main>
          </div>
        </ScraperProvider>
      </body>
    </html>
  );
}
