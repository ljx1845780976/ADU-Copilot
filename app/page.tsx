"use client";

import { useState, useCallback } from "react";
import { UploadZone } from "./components/upload-zone";
import { ParamsForm } from "./components/params-form";
import { AuditResults } from "./components/audit-results";
import { AdvisePanel } from "./components/advise-panel";
import { Hero } from "./components/hero";
import { useAuth } from "./providers/auth-provider";
import { useLanguage } from "./providers/language-provider";
import { tl } from "@/lib/i18n";
import { runAudit, getAdvice } from "@/lib/api";
import { toast } from "./components/use-toast";

type ParamData = Record<string, unknown>;
type AuditItem = Record<string, unknown>;
type RadarItem = Record<string, unknown>;

export default function Home() {
  const { token, setCredits } = useAuth();
  const { lang } = useLanguage();

  const [extractedData, setExtractedData] = useState<ParamData | null>(null);
  const [auditData, setAuditData] = useState<{
    radar: RadarItem[];
    auditResults: AuditItem[];
    failedItems: AuditItem[];
    creditsRemaining: number;
    refUrl: string;
    refWebsite: string;
  } | null>(null);
  const [adviceUnlocked, setAdviceUnlocked] = useState(false);
  const [adviceText, setAdviceText] = useState("");
  const [auditLoading, setAuditLoading] = useState(false);
  const [adviceLoading, setAdviceLoading] = useState(false);

  const handleExtracted = useCallback((data: ParamData) => {
    setExtractedData(data);
    setAuditData(null);
    setAdviceUnlocked(false);
    setAdviceText("");
  }, []);

  const handleAudit = useCallback(
    async (params: ParamData) => {
      if (!token) {
        toast({ title: tl(lang, "toast.loginRequired"), description: tl(lang, "toast.pleaseLogin"), variant: "destructive" });
        return;
      }
      setAuditLoading(true);
      try {
        const result = await runAudit(params, token, lang);
        setCredits(result.credits_remaining);
        setAuditData({
          radar: result.radar as RadarItem[],
          auditResults: result.audit_results as AuditItem[],
          failedItems: result.failed_items as AuditItem[],
          creditsRemaining: result.credits_remaining,
          refUrl: result.official_reference_url || "",
          refWebsite: result.official_reference_website || "",
        });
      } catch (e) {
        toast({ title: tl(lang, "toast.auditFailed"), description: e instanceof Error ? e.message : "Audit failed", variant: "destructive" });
      } finally {
        setAuditLoading(false);
      }
    },
    [token, setCredits, lang]
  );

  const handleUnlockAdvice = useCallback(async () => {
    if (!token || !extractedData || !auditData?.failedItems.length) return;
    setAdviceLoading(true);
    try {
      const result = await getAdvice(
        extractedData,
        auditData.failedItems,
        token,
        lang
      );
      setCredits(result.credits_remaining);
      setAdviceText(result.advice);
      setAdviceUnlocked(true);
      setAuditData((prev) =>
        prev ? { ...prev, creditsRemaining: result.credits_remaining } : null
      );
    } catch (e) {
      toast({ title: tl(lang, "toast.adviceFailed"), description: e instanceof Error ? e.message : "Advice generation failed", variant: "destructive" });
    } finally {
      setAdviceLoading(false);
    }
  }, [token, extractedData, auditData, setCredits, lang]);

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 space-y-6">
      {/* Hero — only before any file is uploaded */}
      {!extractedData && !auditData && <Hero />}

      <section>
        <h2 className="text-lg font-semibold mb-3">{tl(lang, "page.section1")}</h2>
        <UploadZone onExtracted={handleExtracted} disabled={auditLoading} />
      </section>

      {extractedData && (
        <section>
          <h2 className="text-lg font-semibold mb-3">{tl(lang, "page.section2")}</h2>
          <ParamsForm
            key={JSON.stringify(extractedData)}
            data={extractedData}
            onAudit={handleAudit}
            disabled={auditLoading || !token}
          />
        </section>
      )}

      {auditLoading && (
        <section className="flex items-center justify-center py-8">
          <div className="flex items-center gap-3 text-muted-foreground">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            {tl(lang, "audit.loading")}
          </div>
        </section>
      )}

      {auditData && (
        <section>
          <h2 className="text-lg font-semibold mb-3">{tl(lang, "page.section3")}</h2>
          <AuditResults
            radar={auditData.radar as Array<{ axis: string; value: number; max: number; weight: number }>}
            auditResults={
              auditData.auditResults as Array<{
                rule: string;
                is_compliant: boolean;
                actual: string;
                required: string;
                citation: string;
              }>
            }
            failedItems={
              auditData.failedItems as Array<{
                rule: string;
                is_compliant: boolean;
                actual: string;
                required: string;
                citation: string;
              }>
            }
            creditsRemaining={auditData.creditsRemaining}
            refUrl={auditData.refUrl}
            refWebsite={auditData.refWebsite}
          />
        </section>
      )}

      {auditData && (
        <section>
          <h2 className="text-lg font-semibold mb-3">{tl(lang, "page.section4")}</h2>
          <AdvisePanel
            failedCount={auditData.failedItems.length}
            unlocked={adviceUnlocked}
            advice={adviceText}
            creditsRemaining={auditData.creditsRemaining}
            onUnlock={handleUnlockAdvice}
            loading={adviceLoading}
          />
        </section>
      )}
    </main>
  );
}
