import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/layout/Sidebar";
import DoodleBackground from "@/components/layout/DoodleBackground";
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
  title: "Akademik Trend Analiz Sistemi",
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
        <DoodleBackground />
        <ScraperProvider>
          <div className="flex min-h-screen relative z-10">
            <Sidebar />
            <main className="ml-20 flex-1 p-8">
              {children}
            </main>
          </div>
        </ScraperProvider>
      </body>
    </html>
  );
}
