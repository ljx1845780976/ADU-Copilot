"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useLanguage } from "@/app/providers/language-provider";
import { tl } from "@/lib/i18n";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Lock, Sparkles, Loader2, Download } from "lucide-react";

interface AdvisePanelProps {
  failedCount: number;
  unlocked: boolean;
  advice: string;
  creditsRemaining: number;
  onUnlock: () => void;
  loading?: boolean;
}

export function AdvisePanel({
  failedCount,
  unlocked,
  advice,
  creditsRemaining,
  onUnlock,
  loading = false,
}: AdvisePanelProps) {
  const { lang } = useLanguage();

  if (failedCount === 0) {
    return (
      <Card className="border-green-200 bg-green-50/50">
        <CardHeader>
          <CardTitle className="text-base text-green-800">
            {tl(lang, "advise.allPassed")}
          </CardTitle>
          <CardDescription className="text-green-700">
            {tl(lang, "advise.allPassedDesc")}
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <Sparkles className="h-4 w-4" />
          {tl(lang, "advise.aiAdvice")}
        </CardTitle>
        <CardDescription>
          {tl(lang, "advise.adviceDesc", { n: failedCount })}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {unlocked ? (
          <>
            <div className="prose prose-sm max-w-none text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{advice}</ReactMarkdown>
            </div>
            <div className="mt-4 flex justify-end">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  const blob = new Blob([advice], { type: "text/markdown" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = "adu-advice.md";
                  a.click();
                  URL.revokeObjectURL(url);
                }}
              >
                <Download className="mr-2 h-4 w-4" />
                {tl(lang, "advise.exportMd")}
              </Button>
            </div>
          </>
        ) : (
          <div className="relative">
            <div className="blur-sm select-none space-y-3">
              <p className="text-sm">
                {lang === "zh"
                  ? "要解决独立 ADU 高度超标问题，请考虑将拟建高度从 18 英尺降至 16 英尺以下。根据加州政府法规 § 66321(b)(4)(A)，地方政府必须允许独立 ADU 至少 16 英尺的高度。如果在主要公交站点半英里范围内，根据 § 66321(b)(4)(B) 可允许最高 18 英尺。"
                  : "To resolve the detached ADU height exceedance, consider reducing the proposed height from 18 ft to 16 ft or less. Per Gov. Code § 66321(b)(4)(A), local agencies must allow at least 16 ft for detached ADUs. If within one-half mile of a major transit stop, up to 18 ft must be allowed per § 66321(b)(4)(B)."}
              </p>
              <p className="text-sm">
                {lang === "zh"
                  ? "对于后退退距问题，确保建筑距离后地界线至少 4 英尺。根据加州政府法规 § 66314(d)(7) 和 HCD 手册第 37 页，地方政府不得要求 ADU 退距超过 4 英尺。"
                  : "For the rear setback issue, ensure the structure is placed at least 4 ft from the rear lot line. Local agencies may not require more than 4 ft for ADU setbacks per Gov. Code § 66314(d)(7) and HCD Handbook p. 37."}
              </p>
            </div>
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-background/60 rounded-md">
              <Lock className="h-8 w-8 text-muted-foreground mb-3" />
              <p className="text-sm font-medium text-center mb-4">
                {tl(lang, "advise.unlockHint")}
              </p>
              <Button
                onClick={onUnlock}
                disabled={creditsRemaining < 50 || loading}
              >
                {loading ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="mr-2 h-4 w-4" />
                )}
                {loading ? tl(lang, "advise.generating") : tl(lang, "advise.unlock")}
              </Button>
              {creditsRemaining < 50 && (
                <p className="text-xs text-destructive mt-2">
                  {tl(lang, "advise.insufficient", { n: creditsRemaining })}
                </p>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
