import type { Metadata } from "next";
import { AuthProvider } from "./providers/auth-provider";
import { LanguageProvider } from "./providers/language-provider";
import { Navbar } from "./components/navbar";
import { Splash } from "./components/splash";
import { Toaster } from "./components/toaster";
import "./globals.css";

export const metadata: Metadata = {
  title: "ADU Copilot AI",
  description: "California ADU Compliance AI Audit Tool",
  icons: {
    icon: [
      { url: "/favicon-16x16.png", sizes: "16x16", type: "image/png" },
      { url: "/favicon-32x32.png", sizes: "32x32", type: "image/png" },
    ],
    apple: "/apple-touch-icon.png",
    other: [{ url: "/favicon.ico" }],
  },
  manifest: "/site.webmanifest",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background antialiased">
        <LanguageProvider>
          <Splash>
            <AuthProvider>
              <Navbar />
              {children}
              <Toaster />
            </AuthProvider>
          </Splash>
        </LanguageProvider>
      </body>
    </html>
  );
}
