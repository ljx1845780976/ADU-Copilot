"use client";

import { useState, useCallback, useEffect } from "react";
import { Upload, FileText, Loader2, AlertCircle, Check } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useLanguage } from "@/app/providers/language-provider";
import { tl } from "@/lib/i18n";
import { extractFromPdf } from "@/lib/api";
import { PDFDocument } from "pdf-lib";

const MAX_SIZE = 5 * 1024 * 1024; // 5 MB

interface UploadZoneProps {
  onExtracted: (data: Record<string, unknown>) => void;
  disabled?: boolean;
}

type Step = "idle" | "selecting" | "extracting" | "done" | "error";

export function UploadZone({ onExtracted, disabled }: UploadZoneProps) {
  const { lang } = useLanguage();
  const [dragOver, setDragOver] = useState(false);
  const [step, setStep] = useState<Step>("idle");
  const [fileName, setFileName] = useState("");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");

  // Page selection state
  const [totalPages, setTotalPages] = useState(0);
  const [selectedPages, setSelectedPages] = useState<Set<number>>(new Set());
  const [originalFile, setOriginalFile] = useState<File | null>(null);

  // Reset selectedPages when totalPages changes
  useEffect(() => {
    if (totalPages > 0) {
      setSelectedPages(new Set(Array.from({ length: totalPages }, (_, i) => i + 1)));
    }
  }, [totalPages]);

  const togglePage = (page: number) => {
    setSelectedPages((prev) => {
      const next = new Set(prev);
      if (next.has(page)) {
        if (next.size > 1) next.delete(page);
      } else {
        next.add(page);
      }
      return next;
    });
  };

  const selectAll = () => setSelectedPages(new Set(Array.from({ length: totalPages }, (_, i) => i + 1)));
  const deselectAll = () => {
    // Keep at least page 1
    setSelectedPages(new Set([1]));
  };

  const extractSelectedPages = async (file: File, pages: Set<number>): Promise<File> => {
    const arrayBuffer = await file.arrayBuffer();
    const srcDoc = await PDFDocument.load(arrayBuffer);
    const newDoc = await PDFDocument.create();

    const pageIndices = Array.from(pages)
      .sort((a, b) => a - b)
      .map((p) => p - 1); // Convert to 0-based

    const copiedPages = await newDoc.copyPages(srcDoc, pageIndices);
    copiedPages.forEach((p) => newDoc.addPage(p));

    const pdfBytes = await newDoc.save();
    const blob = new Blob([pdfBytes as BlobPart], { type: "application/pdf" });
    return new File([blob], file.name, { type: "application/pdf" });
  };

  const handleConfirmSelection = async () => {
    if (!originalFile || selectedPages.size === 0) return;
    setStep("extracting");
    setProgress(10);

    const interval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 70) { clearInterval(interval); return 70; }
        return prev + Math.random() * 15;
      });
    }, 800);

    try {
      const trimmedFile = await extractSelectedPages(originalFile, selectedPages);
      clearInterval(interval);
      setProgress(70);

      const result = await extractFromPdf(trimmedFile, lang);
      setProgress(100);
      setTimeout(() => {
        setStep("done");
        setProgress(0);
        onExtracted(result.data || {});
      }, 400);
    } catch (e) {
      clearInterval(interval);
      setError(e instanceof Error ? e.message : "Extraction failed");
      setStep("error");
    }
  };

  const handleFile = useCallback(
    async (file: File) => {
      if (!file.name.toLowerCase().endsWith(".pdf")) return;
      setFileName(file.name);
      setError("");

      // Large file: show page selector
      if (file.size > MAX_SIZE) {
        try {
          const arrayBuffer = await file.arrayBuffer();
          const pdfDoc = await PDFDocument.load(arrayBuffer);
          const pages = pdfDoc.getPageCount();
          setTotalPages(pages);
          setOriginalFile(file);
          setStep("selecting");
        } catch {
          setError("Failed to read PDF. The file may be corrupted.");
          setStep("error");
        }
        return;
      }

      // Small file: extract directly
      setStep("extracting");
      setProgress(10);
      const interval = setInterval(() => {
        setProgress((prev) => {
          if (prev >= 90) { clearInterval(interval); return 90; }
          return prev + Math.random() * 15;
        });
      }, 800);

      try {
        const result = await extractFromPdf(file, lang);
        clearInterval(interval);
        setProgress(100);
        setTimeout(() => {
          setStep("done");
          setProgress(0);
          onExtracted(result.data || {});
        }, 400);
      } catch (e) {
        clearInterval(interval);
        setError(e instanceof Error ? e.message : "Extraction failed");
        setStep("error");
      }
    },
    [onExtracted]
  );

  // Build ordered page array for rendering
  const orderedPages = Array.from(selectedPages).sort((a, b) => a - b);

  return (
    <Card>
      <CardContent className="pt-6">
        {/* Page Selector View */}
        {step === "selecting" ? (
          <div className="space-y-4">
            <div className="flex items-start gap-3 rounded-md border border-amber-200 bg-amber-50 p-4">
              <AlertCircle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-amber-800">Large File Detected</p>
                <p className="text-sm text-amber-700 mt-1">
                  This PDF has <strong>{totalPages}</strong> pages and is larger than 5 MB.
                  Select the pages you need to speed up parsing.
                </p>
              </div>
            </div>

            {/* Quick actions */}
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">
                {selectedPages.size} of {totalPages} pages selected
              </span>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={selectAll}>Select All</Button>
                <Button variant="outline" size="sm" onClick={deselectAll}>Deselect All</Button>
              </div>
            </div>

            {/* Page grid */}
            <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 gap-2 max-h-64 overflow-y-auto p-2 border rounded-md">
              {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => {
                const isSelected = selectedPages.has(page);
                return (
                  <button
                    key={page}
                    type="button"
                    onClick={() => togglePage(page)}
                    className={cn(
                      "relative flex flex-col items-center justify-center rounded-md border-2 p-3 transition-all text-sm",
                      isSelected
                        ? "border-primary bg-primary/10 text-primary font-medium"
                        : "border-muted-foreground/20 text-muted-foreground hover:border-muted-foreground/50"
                    )}
                  >
                    {isSelected && (
                      <Check className="absolute top-1 right-1 h-3 w-3 text-primary" />
                    )}
                    <span className="text-lg font-bold">{page}</span>
                  </button>
                );
              })}
            </div>

            {/* Confirm / Cancel */}
            <div className="flex gap-3 justify-end">
              <Button
                variant="ghost"
                onClick={() => {
                  setStep("idle");
                  setOriginalFile(null);
                  setTotalPages(0);
                }}
              >
                Cancel
              </Button>
              <Button onClick={handleConfirmSelection} disabled={selectedPages.size === 0}>
                Parse Selected Pages ({selectedPages.size})
              </Button>
            </div>
          </div>
        ) : (
          /* Drop Zone */
          <div
            onDragOver={(e) => {
              e.preventDefault();
              if (!disabled && step !== "extracting") setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              const file = e.dataTransfer.files?.[0];
              if (file) handleFile(file);
            }}
            className={cn(
              "relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-12 transition-colors",
              dragOver && "border-primary bg-primary/5",
              (disabled || step === "extracting") && "opacity-50 pointer-events-none",
              !dragOver && step !== "error" && "border-muted-foreground/25",
              step === "error" && "border-destructive/50"
            )}
          >
            {step === "extracting" ? (
              <div className="flex flex-col items-center gap-4 w-full max-w-xs">
                <Loader2 className="h-10 w-10 animate-spin text-primary" />
                <p className="text-sm text-muted-foreground text-center">
                  {tl(lang, "upload.extracting")} {fileName}...
                </p>
                <Progress value={progress} className="w-full" />
              </div>
            ) : step === "error" ? (
              <div className="flex flex-col items-center gap-3">
                <AlertCircle className="h-10 w-10 text-destructive" />
                <p className="text-sm font-medium text-destructive">Extraction Failed</p>
                <p className="text-xs text-muted-foreground text-center max-w-xs">{error}</p>
                <button
                  type="button"
                  className="text-xs text-primary hover:underline"
                  onClick={() => { setStep("idle"); setError(""); }}
                >
                  Try again
                </button>
              </div>
            ) : step === "done" ? (
              <div className="flex flex-col items-center gap-3">
                <FileText className="h-10 w-10 text-green-600" />
                <p className="text-sm font-medium">{fileName}</p>
                <p className="text-xs text-muted-foreground">
                  {tl(lang, "upload.complete")}
                </p>
                <label className="cursor-pointer text-xs text-primary hover:underline mt-1">
                  {tl(lang, "upload.reupload")}
                  <input
                    type="file"
                    accept=".pdf"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) handleFile(f);
                    }}
                  />
                </label>
              </div>
            ) : (
              <>
                <Upload className="h-10 w-10 text-muted-foreground mb-4" />
                <p className="text-sm font-medium">{tl(lang, "upload.dropHint")}</p>
                <p className="text-xs text-muted-foreground mt-1">{tl(lang, "upload.clickHint")}</p>
                <input
                  type="file"
                  accept=".pdf"
                  className="absolute inset-0 opacity-0 cursor-pointer"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleFile(file);
                  }}
                />
              </>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
