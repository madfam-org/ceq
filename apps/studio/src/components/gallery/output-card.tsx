"use client";

/**
 * Output Card
 *
 * Displays a single output with preview, download, and share actions.
 */

import { useState } from "react";
import Image from "next/image";
import {
  Download,
  Share2,
  ExternalLink,
  Image as ImageIcon,
  Video,
  File,
  MoreVertical,
  Copy,
  Check,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { Output } from "@/lib/api";

interface OutputCardProps {
  output: Output;
  className?: string;
}

export function OutputCard({ output, className }: OutputCardProps) {
  const { toast } = useToast();
  const [copied, setCopied] = useState(false);

  const isImage = output.file_type.startsWith("image/");
  const isVideo = output.file_type.startsWith("video/");

  const handleDownload = async () => {
    try {
      const response = await fetch(output.storage_uri);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = output.filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      toast({
        title: "Download started",
        description: `Downloading ${output.filename}`,
      });
    } catch {
      toast({
        title: "Download failed",
        description: "Could not download the file. Try again.",
        variant: "destructive",
      });
    }
  };

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(output.storage_uri);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);

      toast({
        title: "Link copied",
        description: "Direct link copied to clipboard",
      });
    } catch {
      toast({
        title: "Copy failed",
        description: "Could not copy link to clipboard",
        variant: "destructive",
      });
    }
  };

  const handleShare = async () => {
    if (navigator.share) {
      try {
        await navigator.share({
          title: output.filename,
          url: output.storage_uri,
        });
      } catch {
        // User cancelled
      }
    } else {
      handleCopyLink();
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <Card className={cn("group overflow-hidden", className)}>
      {/* Preview */}
      <div className="relative aspect-square bg-muted overflow-hidden">
        {isImage && output.preview_url ? (
          <Image
            src={output.preview_url}
            alt={output.filename}
            fill
            className="object-cover transition-transform group-hover:scale-105"
          />
        ) : isVideo ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <Video className="h-12 w-12 text-muted-foreground/50" />
            {output.duration_seconds && (
              <span className="absolute bottom-2 right-2 px-2 py-0.5 bg-black/70 text-white text-xs rounded">
                {formatDuration(output.duration_seconds)}
              </span>
            )}
          </div>
        ) : (
          <div className="absolute inset-0 flex items-center justify-center">
            <File className="h-12 w-12 text-muted-foreground/50" />
          </div>
        )}

        {/* Hover overlay */}
        <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            className="gap-1"
            onClick={handleDownload}
          >
            <Download className="h-3 w-3" />
            Download
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="gap-1"
            onClick={handleShare}
          >
            <Share2 className="h-3 w-3" />
            Share
          </Button>
        </div>

        {/* File type badge */}
        <div className="absolute top-2 left-2">
          <span className="px-2 py-0.5 bg-black/70 text-white text-xs rounded flex items-center gap-1">
            {isImage ? (
              <ImageIcon className="h-3 w-3" />
            ) : isVideo ? (
              <Video className="h-3 w-3" />
            ) : (
              <File className="h-3 w-3" />
            )}
            {output.file_type.split("/")[1].toUpperCase()}
          </span>
        </div>

        {/* Dimensions */}
        {output.width && output.height && (
          <span className="absolute top-2 right-2 px-2 py-0.5 bg-black/70 text-white text-xs rounded">
            {output.width}x{output.height}
          </span>
        )}
      </div>

      {/* Info */}
      <div className="p-3 flex items-center justify-between">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium truncate" title={output.filename}>
            {output.filename}
          </p>
          <p className="text-xs text-muted-foreground">
            {formatFileSize(output.file_size_bytes)}
          </p>
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <MoreVertical className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={handleDownload}>
              <Download className="h-4 w-4 mr-2" />
              Download
            </DropdownMenuItem>
            <DropdownMenuItem onClick={handleCopyLink}>
              {copied ? (
                <Check className="h-4 w-4 mr-2" />
              ) : (
                <Copy className="h-4 w-4 mr-2" />
              )}
              Copy link
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <a
                href={output.storage_uri}
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLink className="h-4 w-4 mr-2" />
                Open in new tab
              </a>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </Card>
  );
}

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}
