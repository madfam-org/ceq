"use client";

/**
 * Template Run Form
 *
 * Auto-generates form fields from template input_schema.
 * Supports: text, number, boolean, select, image upload.
 */

import { useState, useCallback } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Play, Loader2, Cpu, Zap, GitFork, AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { Template, InputSchemaField, runTemplate, forkTemplate } from "@/lib/api";

interface TemplateRunFormProps {
  template: Template;
  className?: string;
}

export function TemplateRunForm({ template, className }: TemplateRunFormProps) {
  const router = useRouter();
  const { toast } = useToast();
  const queryClient = useQueryClient();

  // Initialize form values from defaults
  const [formValues, setFormValues] = useState<Record<string, unknown>>(() => {
    const initial: Record<string, unknown> = {};
    Object.entries(template.input_schema).forEach(([key, field]) => {
      if (field.default !== undefined) {
        initial[key] = field.default;
      } else {
        // Set type-appropriate defaults
        switch (field.type) {
          case "string":
            initial[key] = "";
            break;
          case "int":
            initial[key] = field.min ?? 0;
            break;
          case "float":
            initial[key] = field.min ?? 0.0;
            break;
          case "bool":
            initial[key] = false;
            break;
          case "select":
            initial[key] = field.options?.[0] ?? "";
            break;
          default:
            initial[key] = "";
        }
      }
    });
    return initial;
  });

  const runMutation = useMutation({
    mutationFn: () =>
      runTemplate(template.id, { input_params: formValues }),
    onSuccess: (result) => {
      toast({
        title: "Transmutation initiated",
        description: `Job ${result.job_id.slice(0, 8)}... has entered the queue.`,
      });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      router.push(`/queue`);
    },
    onError: (error) => {
      toast({
        title: "Chaos prevailed",
        description: error instanceof Error ? error.message : "Failed to run template",
        variant: "destructive",
      });
    },
  });

  const forkMutation = useMutation({
    mutationFn: () => forkTemplate(template.id),
    onSuccess: (workflow) => {
      toast({
        title: "Template forked",
        description: "A new workflow has been created from this template.",
      });
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      router.push(`/workflows/${workflow.id}`);
    },
    onError: (error) => {
      toast({
        title: "Fork failed",
        description: error instanceof Error ? error.message : "Failed to fork template",
        variant: "destructive",
      });
    },
  });

  const updateValue = useCallback((key: string, value: unknown) => {
    setFormValues((prev) => ({ ...prev, [key]: value }));
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    runMutation.mutate();
  };

  const isLoading = runMutation.isPending || forkMutation.isPending;

  return (
    <form onSubmit={handleSubmit} className={cn("space-y-6", className)}>
      {/* Template Info Header */}
      <div className="space-y-3 pb-4 border-b border-border">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-xl font-semibold text-foreground">
              {template.name}
            </h2>
            {template.description && (
              <p className="text-sm text-muted-foreground mt-1">
                {template.description}
              </p>
            )}
          </div>
          <Badge variant="outline" className="capitalize">
            {template.category}
          </Badge>
        </div>

        {/* Requirements */}
        <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <Cpu className="h-3 w-3" />
            {template.vram_requirement_gb}GB VRAM
          </span>
          <span className="flex items-center gap-1">
            <Zap className="h-3 w-3" />
            {template.run_count.toLocaleString()} runs
          </span>
          <span className="flex items-center gap-1">
            <GitFork className="h-3 w-3" />
            {template.fork_count.toLocaleString()} forks
          </span>
        </div>

        {/* Model Requirements */}
        {template.model_requirements.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {template.model_requirements.map((model) => (
              <Badge key={model} variant="secondary" className="text-xs">
                {model}
              </Badge>
            ))}
          </div>
        )}
      </div>

      {/* Generated Form Fields */}
      <div className="space-y-4">
        {Object.entries(template.input_schema).map(([key, field]) => (
          <FormField
            key={key}
            name={key}
            field={field}
            value={formValues[key]}
            onChange={(value) => updateValue(key, value)}
          />
        ))}
      </div>

      {/* No inputs message */}
      {Object.keys(template.input_schema).length === 0 && (
        <div className="flex items-center gap-2 p-4 rounded-lg bg-muted/50 text-muted-foreground">
          <AlertCircle className="h-4 w-4" />
          <span className="text-sm">
            This template has no configurable inputs.
          </span>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex gap-3 pt-4 border-t border-border">
        <Button
          type="submit"
          disabled={isLoading}
          className="flex-1 bg-entropy hover:bg-entropy/90"
        >
          {runMutation.isPending ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Initiating...
            </>
          ) : (
            <>
              <Play className="h-4 w-4 mr-2" />
              Run Template
            </>
          )}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={isLoading}
          onClick={() => forkMutation.mutate()}
        >
          {forkMutation.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <>
              <GitFork className="h-4 w-4 mr-2" />
              Fork
            </>
          )}
        </Button>
      </div>
    </form>
  );
}

// Individual form field component
interface FormFieldProps {
  name: string;
  field: InputSchemaField;
  value: unknown;
  onChange: (value: unknown) => void;
}

function FormField({ name, field, value, onChange }: FormFieldProps) {
  const label = field.label || formatLabel(name);
  const id = `field-${name}`;

  switch (field.type) {
    case "string":
      // Use textarea for longer text fields
      const isLongText =
        name.toLowerCase().includes("prompt") ||
        name.toLowerCase().includes("description") ||
        name.toLowerCase().includes("text");

      return (
        <div className="space-y-2">
          <Label htmlFor={id}>{label}</Label>
          {isLongText ? (
            <Textarea
              id={id}
              value={String(value || "")}
              onChange={(e) => onChange(e.target.value)}
              placeholder={field.description}
              className="min-h-[100px] resize-y"
            />
          ) : (
            <Input
              id={id}
              type="text"
              value={String(value || "")}
              onChange={(e) => onChange(e.target.value)}
              placeholder={field.description}
            />
          )}
          {field.description && !isLongText && (
            <p className="text-xs text-muted-foreground">{field.description}</p>
          )}
        </div>
      );

    case "int":
      const intValue = Number(value) || 0;
      const hasIntRange = field.min !== undefined && field.max !== undefined;

      return (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor={id}>{label}</Label>
            <span className="text-sm text-muted-foreground tabular-nums">
              {intValue}
            </span>
          </div>
          {hasIntRange ? (
            <Slider
              id={id}
              value={[intValue]}
              onValueChange={([v]) => onChange(Math.round(v))}
              min={field.min}
              max={field.max}
              step={field.step || 1}
              className="py-2"
            />
          ) : (
            <Input
              id={id}
              type="number"
              value={intValue}
              onChange={(e) => onChange(parseInt(e.target.value) || 0)}
              min={field.min}
              max={field.max}
              step={field.step || 1}
            />
          )}
          {field.description && (
            <p className="text-xs text-muted-foreground">{field.description}</p>
          )}
        </div>
      );

    case "float":
      const floatValue = Number(value) || 0;
      const hasFloatRange = field.min !== undefined && field.max !== undefined;

      return (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor={id}>{label}</Label>
            <span className="text-sm text-muted-foreground tabular-nums">
              {floatValue.toFixed(2)}
            </span>
          </div>
          {hasFloatRange ? (
            <Slider
              id={id}
              value={[floatValue]}
              onValueChange={([v]) => onChange(v)}
              min={field.min}
              max={field.max}
              step={field.step || 0.01}
              className="py-2"
            />
          ) : (
            <Input
              id={id}
              type="number"
              value={floatValue}
              onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
              min={field.min}
              max={field.max}
              step={field.step || 0.01}
            />
          )}
          {field.description && (
            <p className="text-xs text-muted-foreground">{field.description}</p>
          )}
        </div>
      );

    case "bool":
      return (
        <div className="flex items-center justify-between py-2">
          <div className="space-y-0.5">
            <Label htmlFor={id}>{label}</Label>
            {field.description && (
              <p className="text-xs text-muted-foreground">{field.description}</p>
            )}
          </div>
          <Switch
            id={id}
            checked={Boolean(value)}
            onCheckedChange={(checked) => onChange(checked)}
          />
        </div>
      );

    case "select":
      return (
        <div className="space-y-2">
          <Label htmlFor={id}>{label}</Label>
          <Select
            value={String(value || "")}
            onValueChange={(v) => onChange(v)}
          >
            <SelectTrigger id={id}>
              <SelectValue placeholder={`Select ${label.toLowerCase()}`} />
            </SelectTrigger>
            <SelectContent>
              {field.options?.map((option) => (
                <SelectItem key={option} value={option}>
                  {option}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {field.description && (
            <p className="text-xs text-muted-foreground">{field.description}</p>
          )}
        </div>
      );

    case "image":
      return (
        <div className="space-y-2">
          <Label htmlFor={id}>{label}</Label>
          <Input
            id={id}
            type="file"
            accept="image/*"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) {
                // For now, just store the file name
                // In production, this would upload to R2
                onChange(file.name);
              }
            }}
            className="cursor-pointer"
          />
          {field.description && (
            <p className="text-xs text-muted-foreground">{field.description}</p>
          )}
        </div>
      );

    default:
      return (
        <div className="space-y-2">
          <Label htmlFor={id}>{label}</Label>
          <Input
            id={id}
            type="text"
            value={String(value || "")}
            onChange={(e) => onChange(e.target.value)}
            placeholder={field.description}
          />
        </div>
      );
  }
}

// Convert snake_case to Title Case
function formatLabel(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}
