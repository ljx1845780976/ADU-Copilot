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
