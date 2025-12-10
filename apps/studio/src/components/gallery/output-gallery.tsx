"use client";

/**
 * Output Gallery
 *
 * Displays a grid of outputs with lightbox viewing.
 */

import { useState } from "react";
import Image from "next/image";
import {
  X,
  ChevronLeft,
  ChevronRight,
  Download,
  Share2,
  ZoomIn,
  ZoomOut,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { OutputCard } from "./output-card";
import { cn } from "@/lib/utils";
import { Output } from "@/lib/api";

interface OutputGalleryProps {
  outputs: Output[];
  className?: string;
}

export function OutputGallery({ outputs, className }: OutputGalleryProps) {
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const [zoom, setZoom] = useState(1);

  const openLightbox = (index: number) => {
    setLightboxIndex(index);
    setZoom(1);
  };

  const closeLightbox = () => {
    setLightboxIndex(null);
    setZoom(1);
  };

  const goToPrev = () => {
    if (lightboxIndex !== null && lightboxIndex > 0) {
      setLightboxIndex(lightboxIndex - 1);
      setZoom(1);
    }
  };

  const goToNext = () => {
    if (lightboxIndex !== null && lightboxIndex < outputs.length - 1) {
      setLightboxIndex(lightboxIndex + 1);
      setZoom(1);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") closeLightbox();
    if (e.key === "ArrowLeft") goToPrev();
    if (e.key === "ArrowRight") goToNext();
  };

  const currentOutput = lightboxIndex !== null ? outputs[lightboxIndex] : null;

  // Filter to only show image outputs in lightbox-able grid
  const imageOutputs = outputs.filter((o) => o.file_type.startsWith("image/"));

  return (
    <>
      {/* Grid */}
      <div
        className={cn(
          "grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4",
          className
        )}
      >
        {outputs.map((output, index) => (
          <div
            key={output.id}
            onClick={() => {
              if (output.file_type.startsWith("image/")) {
                const imageIndex = imageOutputs.findIndex(
                  (o) => o.id === output.id
                );
                openLightbox(imageIndex);
              }
            }}
            className={cn(
              output.file_type.startsWith("image/") &&
                "cursor-pointer"
            )}
          >
            <OutputCard output={output} />
          </div>
        ))}
      </div>

      {/* Lightbox */}
      {lightboxIndex !== null && currentOutput && (
        <div
          className="fixed inset-0 z-50 bg-black/95 flex items-center justify-center"
          onKeyDown={handleKeyDown}
          tabIndex={0}
          role="dialog"
          aria-modal="true"
          aria-label="Image lightbox"
        >
          {/* Close button */}
          <Button
            variant="ghost"
            size="icon"
            className="absolute top-4 right-4 text-white hover:bg-white/10 z-50"
            onClick={closeLightbox}
          >
            <X className="h-6 w-6" />
          </Button>

          {/* Navigation */}
          {lightboxIndex > 0 && (
            <Button
              variant="ghost"
              size="icon"
              className="absolute left-4 top-1/2 -translate-y-1/2 text-white hover:bg-white/10 z-50"
              onClick={goToPrev}
            >
              <ChevronLeft className="h-8 w-8" />
            </Button>
          )}
          {lightboxIndex < imageOutputs.length - 1 && (
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-4 top-1/2 -translate-y-1/2 text-white hover:bg-white/10 z-50"
              onClick={goToNext}
            >
              <ChevronRight className="h-8 w-8" />
            </Button>
          )}

          {/* Image */}
          <div
            className="relative max-w-[90vw] max-h-[90vh] overflow-hidden"
            style={{ transform: `scale(${zoom})` }}
          >
            {imageOutputs[lightboxIndex].preview_url && (
              <Image
                src={imageOutputs[lightboxIndex].storage_uri}
                alt={imageOutputs[lightboxIndex].filename}
                width={imageOutputs[lightboxIndex].width || 1024}
                height={imageOutputs[lightboxIndex].height || 1024}
                className="max-w-full max-h-[90vh] object-contain"
                priority
              />
            )}
          </div>

          {/* Controls */}
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-2 bg-black/50 rounded-lg px-4 py-2">
            <Button
              variant="ghost"
              size="icon"
              className="text-white hover:bg-white/10"
              onClick={() => setZoom(Math.max(0.5, zoom - 0.25))}
            >
              <ZoomOut className="h-5 w-5" />
            </Button>
            <span className="text-white text-sm min-w-[60px] text-center">
              {Math.round(zoom * 100)}%
            </span>
            <Button
              variant="ghost"
              size="icon"
              className="text-white hover:bg-white/10"
              onClick={() => setZoom(Math.min(3, zoom + 0.25))}
            >
              <ZoomIn className="h-5 w-5" />
            </Button>
            <div className="w-px h-6 bg-white/20 mx-2" />
            <Button
              variant="ghost"
              size="icon"
              className="text-white hover:bg-white/10"
              onClick={async () => {
                const output = imageOutputs[lightboxIndex];
                const response = await fetch(output.storage_uri);
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = output.filename;
                a.click();
                window.URL.revokeObjectURL(url);
              }}
            >
              <Download className="h-5 w-5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="text-white hover:bg-white/10"
              onClick={async () => {
                const output = imageOutputs[lightboxIndex];
                if (navigator.share) {
                  await navigator.share({
                    title: output.filename,
                    url: output.storage_uri,
                  });
                } else {
                  await navigator.clipboard.writeText(output.storage_uri);
                }
              }}
            >
              <Share2 className="h-5 w-5" />
            </Button>
          </div>

          {/* Counter */}
          <div className="absolute top-4 left-4 text-white text-sm bg-black/50 px-3 py-1 rounded">
            {lightboxIndex + 1} / {imageOutputs.length}
          </div>

          {/* Filename */}
          <div className="absolute top-4 left-1/2 -translate-x-1/2 text-white text-sm bg-black/50 px-3 py-1 rounded">
            {imageOutputs[lightboxIndex].filename}
          </div>
        </div>
      )}
    </>
  );
}
