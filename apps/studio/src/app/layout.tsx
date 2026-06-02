import type { Metadata } from "next";
import { JetBrains_Mono, Inter } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import { Toaster } from "@/components/ui/sonner";

const fontMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
});

const fontSans = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "ceq | Production Control Plane for Generative Media",
  description:
    "CEQ turns repeatable ComfyUI workflows into deterministic render APIs, galleries, billing-ready credits, and client-safe generative production.",
  metadataBase: new URL("https://ceq.lol"),
  icons: {
    icon: "/favicon.ico",
  },
  openGraph: {
    title: "CEQ Studio — Production Control Plane for Generative Media",
    description:
      "Run reusable templates, preserve seeds, control GPU cost, cache outputs, and ship client-ready image, audio, and 3D assets.",
    url: "https://ceq.lol",
    siteName: "CEQ Studio by MADFAM",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "CEQ Studio — Production Control Plane for Generative Media",
    description:
      "Reusable ComfyUI workflows, deterministic render APIs, cached outputs, and client-safe generative production.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${fontMono.variable} ${fontSans.variable} font-mono antialiased min-h-screen bg-background`}
      >
        <Providers>
          {children}
          <Toaster />
        </Providers>
      </body>
    </html>
  );
}
