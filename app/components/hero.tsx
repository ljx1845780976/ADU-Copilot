"use client";

import { useLanguage } from "@/app/providers/language-provider";
import { tl } from "@/lib/i18n";
import { Upload, ClipboardCheck, Sparkles } from "lucide-react";

export function Hero() {
  const { lang } = useLanguage();

  return (
    <div className="text-center space-y-6 py-8">
      {/* Title */}
      <h1 className="text-4xl font-bold tracking-tight">
        {tl(lang, "hero.title")}
      </h1>
      <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
        {tl(lang, "hero.subtitle")}
      </p>

      {/* Steps */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-3xl mx-auto pt-4">
        <div className="flex flex-col items-center gap-2 p-4 rounded-lg border bg-card">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Upload className="h-5 w-5" />
          </div>
          <h3 className="font-semibold text-sm">{tl(lang, "hero.step1title")}</h3>
          <p className="text-xs text-muted-foreground">{tl(lang, "hero.step1desc")}</p>
        </div>

        <div className="flex flex-col items-center gap-2 p-4 rounded-lg border bg-card">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary">
            <ClipboardCheck className="h-5 w-5" />
          </div>
          <h3 className="font-semibold text-sm">{tl(lang, "hero.step2title")}</h3>
          <p className="text-xs text-muted-foreground">{tl(lang, "hero.step2desc")}</p>
        </div>

        <div className="flex flex-col items-center gap-2 p-4 rounded-lg border bg-card">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Sparkles className="h-5 w-5" />
          </div>
          <h3 className="font-semibold text-sm">{tl(lang, "hero.step3title")}</h3>
          <p className="text-xs text-muted-foreground">{tl(lang, "hero.step3desc")}</p>
        </div>
      </div>
    </div>
  );
}
