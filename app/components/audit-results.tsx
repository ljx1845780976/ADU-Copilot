"use client";

import { useLanguage } from "@/app/providers/language-provider";
import { tl } from "@/lib/i18n";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, XCircle } from "lucide-react";
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

interface RadarItem {
  axis: string;
  value: number;
  max: number;
  weight: number;
}

interface AuditItem {
  rule: string;
  is_compliant: boolean;
  actual: string;
  required: string;
  citation: string;
}

interface AuditResultsProps {
  radar: RadarItem[];
  auditResults: AuditItem[];
  failedItems: AuditItem[];
  creditsRemaining: number;
  refUrl: string;
  refWebsite: string;
}

export function AuditResults({
  radar,
  auditResults,
  failedItems,
  creditsRemaining,
  refUrl,
  refWebsite,
}: AuditResultsProps) {
  const { lang } = useLanguage();
  const chartData = radar.map((r) => ({
    axis: r.axis,
    value: (r.value / r.max) * 100,
    fullMark: 100,
  }));

  return (
    <div className="space-y-4">
      {/* Summary Bar */}
      <Card className="bg-muted/50">
        <CardContent className="py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-green-600" />
              <span className="text-sm">
                <strong>{auditResults.filter((r) => r.is_compliant).length}</strong> {tl(lang, "audit.pass")}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <XCircle className="h-5 w-5 text-red-600" />
              <span className="text-sm">
                <strong>{failedItems.length}</strong> {tl(lang, "audit.fail")}
              </span>
            </div>
          </div>
          <div className="text-sm text-muted-foreground">
            {tl(lang, "audit.creditsLeft")}: <strong className="text-foreground">{creditsRemaining}</strong>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Radar Chart */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{tl(lang, "audit.radar")}</CardTitle>
            <CardDescription>{tl(lang, "audit.radarDesc")}</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={320}>
              <RadarChart data={chartData}>
                <PolarGrid />
                <PolarAngleAxis
                  dataKey="axis"
                  tick={{ fontSize: 11, fill: "#6b7280" }}
                />
                <PolarRadiusAxis
                  angle={90}
                  domain={[0, 100]}
                  tick={{ fontSize: 10 }}
                />
                <Radar
                  name="Compliance"
                  dataKey="value"
                  stroke="#2563eb"
                  fill="#3b82f6"
                  fillOpacity={0.25}
                />
                <Tooltip
                  formatter={(value: number) => [`${value.toFixed(0)}%`, tl(lang, "audit.score")]}
                />
              </RadarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Checklist */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{tl(lang, "audit.checklist")}</CardTitle>
            <CardDescription>{tl(lang, "audit.checklistDesc")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 max-h-[360px] overflow-y-auto">
            {auditResults.map((item, i) => (
              <div
                key={i}
                className={`flex items-start gap-3 rounded-md border p-3 text-sm ${
                  item.is_compliant
                    ? "border-green-200 bg-green-50/50"
                    : "border-red-200 bg-red-50/50"
                }`}
              >
                {item.is_compliant ? (
                  <CheckCircle2 className="h-4 w-4 text-green-600 mt-0.5 shrink-0" />
                ) : (
                  <XCircle className="h-4 w-4 text-red-600 mt-0.5 shrink-0" />
                )}
                <div className="min-w-0">
                  <p className="font-medium">{item.rule}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Actual: {item.actual} | Required: {item.required}
                  </p>
                  <p className="text-xs text-muted-foreground truncate">
                    {item.citation}
                  </p>
                </div>
                <Badge
                  variant={item.is_compliant ? "success" : "destructive"}
                  className="ml-auto shrink-0"
                >
                  {item.is_compliant ? tl(lang, "audit.pass") : tl(lang, "audit.fail")}
                </Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {/* Reference Link */}
      {refWebsite && (
        <div className="flex justify-end">
          <a
            href={refWebsite}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-xs text-primary hover:underline"
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
            {tl(lang, "audit.refHandbook")}
          </a>
        </div>
      )}
    </div>
  );
}
