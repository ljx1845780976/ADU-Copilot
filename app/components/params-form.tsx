"use client";

import { useState } from "react";
import { useLanguage } from "@/app/providers/language-provider";
import { tl } from "@/lib/i18n";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { ChevronDown, ChevronUp, Settings2 } from "lucide-react";

type ParamData = Record<string, unknown>;

interface ParamsFormProps {
  data: ParamData | null;
  onAudit: (params: ParamData) => void;
  disabled?: boolean;
}

const FIELD_CONFIG: {
  key: string;
  label: string;
  type: "text" | "number" | "select" | "switch" | "textarea";
  options?: { value: string; label: string }[];
  hint?: string;
  category?: string;
}[] = [
  { key: "project_address", label: "Project Address", type: "text", category: "Project Info" },
  { key: "apn", label: "APN", type: "text", category: "Project Info" },
  { key: "lot_size_sqft", label: "Lot Size (sq ft)", type: "number", category: "Lot" },
  { key: "adu_type", label: "ADU Type", type: "select", options: [
    { value: "Detached", label: "Detached" },
    { value: "Attached", label: "Attached" },
    { value: "JADU", label: "JADU" },
  ], category: "Basic" },
  { key: "proposed_adu_sqft", label: "Proposed ADU (sq ft)", type: "number", category: "Basic" },
  { key: "proposed_height_ft", label: "Proposed Height (ft)", type: "number", category: "Basic" },
  { key: "stories", label: "Stories", type: "number", category: "Basic" },
  { key: "adu_bedroom_count", label: "Bedrooms", type: "number", category: "Basic" },
  { key: "adu_permitting_track", label: "Permitting Track", type: "select", options: [
    { value: "66314", label: "66314 (Default)" },
    { value: "66323_detached", label: "66323 Detached (800sf max)" },
  ], category: "Basic" },
  { key: "primary_dwelling_sqft", label: "Primary Dwelling (sq ft)", type: "number", category: "Dwelling" },
  { key: "primary_structure_height_ft", label: "Primary Structure Height (ft)", type: "number", category: "Dwelling" },
  { key: "rear_setback_ft", label: "Rear Setback (ft)", type: "number", category: "Setbacks" },
  { key: "side_setback_ft", label: "Side Setback (ft)", type: "number", category: "Setbacks" },
  { key: "front_setback_ft", label: "Front Setback (ft)", type: "number", category: "Setbacks" },
  { key: "separation_from_primary_ft", label: "Separation from Primary (ft)", type: "number", category: "Setbacks" },
  { key: "is_near_transit", label: "Near Transit (½ mile)", type: "switch", category: "Location" },
  { key: "min_ceiling_height_ft", label: "Min Ceiling Height (ft)", type: "number", category: "Interior" },
  { key: "roof_type_notes", label: "Roof Type Notes", type: "text", category: "Other" },
  // JADU-specific fields
  { key: "is_jadu_within_primary_dwelling", label: "JADU within Primary Dwelling", type: "switch", category: "JADU" },
  { key: "jadu_has_separate_entrance", label: "JADU Separate Entrance", type: "switch", category: "JADU" },
  { key: "jadu_has_separate_bathroom", label: "JADU Separate Bathroom", type: "switch", category: "JADU" },
  { key: "jadu_shares_sanitation_with_primary", label: "JADU Shares Sanitation", type: "switch", category: "JADU" },
  { key: "jadu_interior_entrance_to_main", label: "JADU Interior Entrance to Main", type: "switch", category: "JADU" },
  { key: "owner_occupies_primary", label: "Owner Occupies Primary", type: "switch", category: "JADU" },
];

export function ParamsForm({ data, onAudit, disabled }: ParamsFormProps) {
  const { lang } = useLanguage();
  const [formData, setFormData] = useState<ParamData>(data || {});
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    "Basic": true,
  });
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Update formData when data changes
  if (data && Object.keys(formData).length === 0) {
    setFormData(data);
  }

  const updateField = (key: string, value: unknown) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  const categories = [...new Set(FIELD_CONFIG.map((f) => f.category).filter(Boolean))] as string[];

  const visibleFields = FIELD_CONFIG.filter((f) => {
    if (!showAdvanced && ["JADU", "Interior", "Other"].includes(f.category || "")) return false;
    return true;
  });

  const grouped = categories.reduce(
    (acc, cat) => {
      const fields = visibleFields.filter((f) => f.category === cat && formData[f.key] !== undefined);
      if (fields.length > 0) acc[cat] = fields;
      return acc;
    },
    {} as Record<string, typeof FIELD_CONFIG>
  );

  if (!data) return null;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="text-lg">{tl(lang, "params.title")}</CardTitle>
          <CardDescription>{tl(lang, "params.desc")}</CardDescription>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowAdvanced(!showAdvanced)}
        >
          <Settings2 className="mr-2 h-4 w-4" />
          {showAdvanced ? tl(lang, "params.hideAdvanced") : tl(lang, "params.showAdvanced")}
        </Button>
      </CardHeader>
      <CardContent className="space-y-6">
        {Object.entries(grouped).map(([category, fields]) => (
          <div key={category}>
            <button
              type="button"
              className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground mb-3 w-full"
              onClick={() =>
                setExpandedSections((prev) => ({
                  ...prev,
                  [category]: !prev[category],
                }))
              }
            >
              {expandedSections[category] ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
              {tl(lang, `params.section.${category}`)}
            </button>
            {expandedSections[category] !== false && (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {fields.map((field) => (
                  <div key={field.key} className="space-y-1.5">
                    <Label htmlFor={field.key} className="text-xs">
                      {tl(lang, `field.${field.key}`)}
                    </Label>
                    {field.type === "select" ? (
                      <Select
                        value={String(formData[field.key] || "")}
                        onValueChange={(v) => updateField(field.key, v)}
                      >
                        <SelectTrigger id={field.key} className="h-9 text-sm">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {field.options?.map((opt) => (
                            <SelectItem key={opt.value} value={opt.value}>
                              {opt.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    ) : field.type === "switch" ? (
                      <div className="flex items-center gap-2 pt-1">
                        <Switch
                          id={field.key}
                          checked={!!formData[field.key]}
                          onCheckedChange={(v) => updateField(field.key, v)}
                        />
                        <Label htmlFor={field.key} className="text-xs text-muted-foreground cursor-pointer">
                          {formData[field.key] ? tl(lang, "params.yes") : tl(lang, "params.no")}
                        </Label>
                      </div>
                    ) : (
                      <Input
                        id={field.key}
                        type={field.type}
                        value={formData[field.key] === null || formData[field.key] === undefined ? "" : String(formData[field.key])}
                        onChange={(e) =>
                          updateField(
                            field.key,
                            field.type === "number"
                              ? parseFloat(e.target.value) || 0
                              : e.target.value
                          )
                        }
                        className="h-9 text-sm"
                      />
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}

        <Button
          size="lg"
          className="w-full"
          disabled={disabled}
          onClick={() => onAudit(formData)}
        >
          {tl(lang, "params.auditBtn")}
        </Button>
      </CardContent>
    </Card>
  );
}
