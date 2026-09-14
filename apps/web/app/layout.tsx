import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Geist, Geist_Mono } from "next/font/google";
import { AuthProvider } from "@/lib/auth-context";
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
  title: "CaseFlow AI",
  description: "AI research and document intelligence platform.",
};

// A plain, explicit prop type rather than Next.js's generated
// `LayoutProps<"/">` ambient type — that type only exists after a
// build has run once (`.next/types/`), so `tsc --noEmit` on a clean
// checkout (no prior build — exactly what CI does) fails with
// "Cannot find name 'LayoutProps'" before ever reaching `next build`,
// which is what actually generates it. `{ children: ReactNode }` is
// the standard App Router root layout signature and needs nothing
// generated.
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-screen flex-col bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-50">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
