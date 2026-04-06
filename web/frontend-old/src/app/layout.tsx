import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import ThemeProvider from "@/components/ThemeProvider";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
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
  title: {
    default: "NFL Data Engineering | Fantasy Projections & Game Predictions",
    template: "%s | NFL Data Engineering",
  },
  description:
    "Weekly fantasy football projections for QB, RB, WR, TE with floor/ceiling ranges. NFL game predictions with edge detection vs Vegas lines.",
  openGraph: {
    type: "website",
    locale: "en_US",
    siteName: "NFL Data Engineering",
    title: "NFL Data Engineering | Fantasy Projections & Game Predictions",
    description:
      "Weekly fantasy football projections and game predictions powered by historical analytics and ML models.",
  },
  twitter: {
    card: "summary_large_image",
    title: "NFL Data Engineering",
    description:
      "Fantasy football projections and NFL game predictions powered by data analytics.",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="flex min-h-full flex-col bg-background text-foreground">
        <ThemeProvider>
          <Header />
          <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6 lg:px-8">
            {children}
          </main>
          <Footer />
        </ThemeProvider>
      </body>
    </html>
  );
}
