"use client";

import { useAuth } from "@/app/providers/auth-provider";
import { useLanguage } from "@/app/providers/language-provider";
import { tl } from "@/lib/i18n";
import { supabase } from "@/lib/supabase";
import { Button } from "@/components/ui/button";
import { AuthDialog } from "./auth-dialog";
import { LogOut, Coins, Home, Languages } from "lucide-react";

export function Navbar() {
  const { email, credits, loading } = useAuth();
  const { lang, toggleLang } = useLanguage();

  const handleLogout = async () => {
    await supabase.auth.signOut();
  };

  return (
    <nav className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex h-14 max-w-4xl items-center justify-between px-4">
        <div className="flex items-center gap-2 font-semibold text-lg">
          <Home className="h-5 w-5" />
          ADU Copilot AI
        </div>

        <div className="flex items-center gap-2">
          {/* Language Toggle */}
          <Button variant="ghost" size="sm" onClick={toggleLang} title={tl(lang, "lang.label")}>
            <Languages className="h-4 w-4 mr-1" />
            <span className="text-xs">{tl(lang, "lang.label")}</span>
          </Button>

          {!loading && email ? (
            <>
              <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                <Coins className="h-4 w-4" />
                <span className="font-medium text-foreground">{credits}</span>
                {tl(lang, "nav.credits")}
              </div>
              <span className="text-sm text-muted-foreground hidden sm:inline">
                {email.split("@")[0]}
              </span>
              <Button
                variant="ghost"
                size="icon"
                onClick={handleLogout}
                title={tl(lang, "nav.logout")}
              >
                <LogOut className="h-4 w-4" />
              </Button>
            </>
          ) : (
            <AuthDialog>
              <Button variant="default" size="sm" disabled={loading}>
                {tl(lang, "nav.login")}
              </Button>
            </AuthDialog>
          )}

          <Button variant="outline" size="sm" asChild>
            <a
              href="https://store.lemonsqueezy.com/checkout"
              target="_blank"
              rel="noopener noreferrer"
            >
              {tl(lang, "nav.buyCredits")}
            </a>
          </Button>
        </div>
      </div>
    </nav>
  );
}
