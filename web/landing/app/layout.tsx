import type { Metadata, Viewport } from "next";
import { Archivo, Inter, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

const display = Archivo({ subsets: ["latin"], weight: ["700", "800", "900"], variable: "--font-archivo" });
const body = Inter({ subsets: ["latin"], variable: "--font-inter" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-plex" });

export const metadata: Metadata = {
  title: "My Trade Portal — Quotes to invoices, powered by AI",
  description:
    "The AI back office for UK trades. Draft guide-priced quotes from a plain-English description, book the job, send the invoice — from your phone. Join the iOS beta on TestFlight.",
  icons: { icon: "/favicon.png", apple: "/apple-touch-icon.png" },
};

export const viewport: Viewport = {
  themeColor: "#0F1E26",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-GB" className={`${display.variable} ${body.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
