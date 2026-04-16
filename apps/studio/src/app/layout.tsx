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
  title: "ceq | Creative Entropy Quantized",
  description: "Generative AI image pipeline by MADFAM. The skunkworks terminal for the generative avant-garde.",
  metadataBase: new URL("https://ceq.lol"),
  icons: {
    icon: "/favicon.ico",
  },
  openGraph: {
    title: "CEQ Studio — Generative AI Image Pipeline",
    description: "The skunkworks terminal for the generative avant-garde. Wraps ComfyUI with a streamlined, hacker-centric interface.",
    url: "https://ceq.lol",
    siteName: "CEQ Studio by MADFAM",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "CEQ Studio — Generative AI Image Pipeline",
    description: "The skunkworks terminal for the generative avant-garde.",
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
