"use client";

/**
 * Gallery Page
 *
 * Browse all outputs from completed jobs with filtering and search.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Image as ImageIcon,
  Video,
  File,
  Loader2,
  Search,
  Filter,
} from "lucide-react";

import { MainLayout } from "@/components/layout/main-layout";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { OutputGallery } from "@/components/gallery/output-gallery";
import { getGalleryOutputs, getJobs } from "@/lib/api";

const FILE_TYPE_FILTERS = [
  { id: "all", label: "All Files", icon: File },
  { id: "image", label: "Images", icon: ImageIcon },
  { id: "video", label: "Videos", icon: Video },
];

export default function GalleryPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [fileTypeFilter, setFileTypeFilter] = useState("all");

  // Fetch completed jobs to get outputs
  const { data: jobsData, isLoading: jobsLoading } = useQuery({
    queryKey: ["jobs", "completed"],
    queryFn: () => getJobs({ status_filter: "completed", limit: 50 }),
  });

  // Aggregate outputs from completed jobs
  const allOutputs =
    jobsData?.jobs.flatMap((job) => job.outputs || []) || [];

  // Filter outputs
  const filteredOutputs = allOutputs.filter((output) => {
    // File type filter
    if (fileTypeFilter === "image" && !output.file_type.startsWith("image/"))
      return false;
    if (fileTypeFilter === "video" && !output.file_type.startsWith("video/"))
      return false;

    // Search filter
    if (
      searchQuery &&
      !output.filename.toLowerCase().includes(searchQuery.toLowerCase())
    ) {
      return false;
    }

    return true;
  });

  const currentFilter = FILE_TYPE_FILTERS.find((f) => f.id === fileTypeFilter);
  const FilterIcon = currentFilter?.icon || File;

  return (
    <MainLayout>
      <div className="flex flex-col gap-6 p-6">
        <header>
          <div className="flex items-center gap-3 mb-2">
            <ImageIcon className="h-6 w-6 text-primary" />
            <h1 className="text-2xl font-bold">Gallery</h1>
          </div>
          <p className="text-sm text-muted-foreground terminal-text">
            Browse materialized outputs from completed jobs
          </p>
        </header>

        {/* Filters */}
        <div className="flex items-center gap-4">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search outputs..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10"
            />
          </div>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" className="gap-2">
                <Filter className="h-4 w-4" />
                <FilterIcon className="h-4 w-4" />
                {currentFilter?.label}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {FILE_TYPE_FILTERS.map((filter) => (
                <DropdownMenuItem
                  key={filter.id}
                  onClick={() => setFileTypeFilter(filter.id)}
                  className="gap-2"
                >
                  <filter.icon className="h-4 w-4" />
                  {filter.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          <span className="text-sm text-muted-foreground">
            {filteredOutputs.length} output
            {filteredOutputs.length !== 1 ? "s" : ""}
          </span>
        </div>

        {/* Loading state */}
        {jobsLoading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        )}

        {/* Empty state */}
        {!jobsLoading && filteredOutputs.length === 0 && (
          <section className="ceq-card">
            <div className="text-center py-12 text-muted-foreground">
              <ImageIcon className="h-12 w-12 mx-auto mb-4 opacity-50" />
              {searchQuery || fileTypeFilter !== "all" ? (
                <>
                  <p className="terminal-text">No outputs match your filters.</p>
                  <p className="text-sm">Try different search terms or filters.</p>
                </>
              ) : (
                <>
                  <p className="terminal-text">Gallery initializing...</p>
                  <p className="text-sm">
                    Completed job outputs will appear here.
                  </p>
                </>
              )}
            </div>
          </section>
        )}

        {/* Gallery */}
        {!jobsLoading && filteredOutputs.length > 0 && (
          <OutputGallery outputs={filteredOutputs} />
        )}
      </div>
    </MainLayout>
  );
}
