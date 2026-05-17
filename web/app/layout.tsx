import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { Toaster } from "sonner";
import "./globals.css";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { CommandShell } from "./command-shell";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: "AVENGERS",
  description: "Multi-agent daily briefing and command platform.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} min-h-screen antialiased`}>
        <div className="mx-auto flex max-w-[1400px] gap-4 p-4">
          <Sidebar />
          <div className="flex min-w-0 flex-1 flex-col gap-4">
            <Topbar />
            <main className="min-h-[calc(100vh-7rem)] pb-12">{children}</main>
          </div>
        </div>
        <CommandShell />
        <Toaster position="bottom-right" theme="dark" richColors />
      </body>
    </html>
  );
}
