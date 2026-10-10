import type { Metadata } from "next";
import { ThemeProvider, ThemeScript } from "@/components/theme-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "Fathom: document intelligence",
  description: "Ask questions across your documents with hybrid retrieval, reranking and cited answers.",
};

const THEME_KEY = "fathom-theme";

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="dark h-full antialiased" suppressHydrationWarning>
      <head>
        <ThemeScript storageKey={THEME_KEY} />
      </head>
      <body className="h-full">
        <ThemeProvider storageKey={THEME_KEY}>{children}</ThemeProvider>
      </body>
    </html>
  );
}
