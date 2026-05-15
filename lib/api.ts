import type { Lang } from "./i18n";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

function authHeaders(token: string): Record<string, string> {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

/**
 * Extract ADU parameters from a PDF file via the streaming endpoint.
 */
export async function extractFromPdf(
  file: File,
  lang: Lang,
  onProgress?: (pct: number) => void
): Promise<{ status: string; data: Record<string, unknown> }> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_URL}/api/extract?lang=${lang}`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Extraction failed: ${res.status} ${err}`);
  }

  const text = await res.text();
  const jsonStart = text.indexOf("{");
  if (jsonStart === -1) {
    throw new Error("No JSON found in streaming response");
  }
  const json = JSON.parse(text.slice(jsonStart));
  if (json.status === "error") {
    throw new Error(json.detail || "Extraction failed");
  }
  return json;
}

/**
 * Run ADU compliance audit (costs 30 credits).
 */
export async function runAudit(
  params: Record<string, unknown>,
  token: string,
  lang: Lang
): Promise<{
  status: string;
  audit_results: Array<Record<string, unknown>>;
  radar: Array<Record<string, unknown>>;
  failed_items: Array<Record<string, unknown>>;
  failed_count: number;
  credits_remaining: number;
  official_reference_url: string;
  official_reference_website: string;
}> {
  const res = await fetch(`${API_URL}/api/audit?lang=${lang}`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ parameters: params }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Audit failed: ${res.status}`);
  }

  return res.json();
}

/**
 * Get AI remediation advice via streaming (costs 50 credits).
 */
export async function getAdvice(
  params: Record<string, unknown>,
  failedItems: Array<Record<string, unknown>>,
  token: string,
  lang: Lang
): Promise<{
  status: string;
  advice: string;
  credits_deducted: number;
  credits_remaining: number;
}> {
  const res = await fetch(`${API_URL}/api/advise`, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ parameters: params, failed_items: failedItems, lang }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Advice generation failed: ${res.status}`);
  }

  const text = await res.text();
  const jsonStart = text.indexOf("{");
  if (jsonStart === -1) {
    throw new Error("No JSON found in streaming response");
  }
  const json = JSON.parse(text.slice(jsonStart));
  if (json.status === "error") {
    throw new Error(json.detail || "Advice generation failed");
  }
  return json;
}
