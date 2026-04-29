import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tiny Teams with Tokens",
  description: "Status reports for AI-assisted engineering teams",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <div className="mx-auto max-w-7xl px-6 py-8">
          <header className="mb-8 flex items-baseline justify-between border-b border-neutral-200 pb-4 dark:border-neutral-800">
            <a href="/" className="text-lg font-semibold tracking-tight">
              tiny teams with tokens
            </a>
            <span className="text-xs text-neutral-500">poc</span>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
