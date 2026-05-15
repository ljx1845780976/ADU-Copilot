"use client";

import { useState, useEffect } from "react";
import { useLanguage } from "@/app/providers/language-provider";
import { tl } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { ArrowRight } from "lucide-react";

const SPLASH_KEY = "adu-splash-done";

export function Splash({ children }: { children: React.ReactNode }) {
  const [show, setShow] = useState(true);
  const [fading, setFading] = useState(false);
  const { lang } = useLanguage();

  useEffect(() => {
    if (localStorage.getItem(SPLASH_KEY)) {
      setShow(false);
    }
  }, []);

  const handleEnter = () => {
    setFading(true);
    setTimeout(() => {
      localStorage.setItem(SPLASH_KEY, "1");
      setShow(false);
    }, 500);
  };

  if (!show) return <>{children}</>;

  return (
    <>
      {/* Splash Screen */}
      <div
        className={`fixed inset-0 z-50 flex flex-col items-center justify-center transition-opacity duration-500 ${
          fading ? "opacity-0" : "opacity-100"
        }`}
        style={{
          background: `linear-gradient(rgba(0,0,0,0.5), rgba(0,0,0,0.6)), url(/backgroup.png) center/cover no-repeat`,
        }}
      >
        <div className="text-center text-white space-y-6 px-4">
          <h1 className="text-5xl font-bold tracking-tight drop-shadow-lg">
            ADU Copilot AI
          </h1>
          <p className="text-lg text-white/80 max-w-xl mx-auto drop-shadow">
            {tl(lang, "splash.subtitle")}
          </p>
          <Button
            size="lg"
            onClick={handleEnter}
            className="mt-4 text-base px-8 py-6 rounded-full shadow-lg hover:shadow-xl transition-all"
          >
            {tl(lang, "splash.enter")}
            <ArrowRight className="ml-2 h-5 w-5" />
          </Button>
        </div>
      </div>

      {/* Main content (already rendered behind) */}
      {children}
    </>
  );
}
