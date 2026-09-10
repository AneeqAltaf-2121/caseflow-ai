"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, API_URL } from "@/lib/api";
import { getAccessToken } from "@/lib/tokens";
import { useProject } from "@/lib/hooks";
import type { ProjectDocument } from "@/lib/types";
import { ProjectSwitcher } from "@/components/ProjectSwitcher";
import { ProjectNav } from "@/components/ProjectNav";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { Skeleton, SkeletonList } from "@/components/Skeleton";

const STATUS_STYLES: Record<ProjectDocument["status"], string> = {
  uploaded: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300",
  processing: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  ready: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

export default function DocumentsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { project, error: projectError } = useProject(id);

  const [documents, setDocuments] = useState<ProjectDocument[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setDocuments(await api.listDocuments(id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load documents.");
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    try {
      await api.uploadDocument(id, file);
      await load();
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleDownload(doc: ProjectDocument) {
    try {
      const token = getAccessToken();
      const response = await fetch(`${API_URL}/projects/${id}/documents/${doc.id}/download`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) throw new Error("Download failed.");
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = doc.filename;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch {
      alert("Failed to download document.");
    }
  }

  if (projectError) return <ErrorState message={projectError} />;
  if (!project) return <Skeleton className="h-40 w-full" />;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <ProjectSwitcher currentProject={project} />
      <ProjectNav projectId={id} />

      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Documents</h2>
        <label className="cursor-pointer rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900">
          {uploading ? "Uploading…" : "Upload document"}
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.md,.csv,.pdf,.doc,.docx"
            className="hidden"
            disabled={uploading}
            onChange={handleFileChange}
          />
        </label>
      </div>
      {uploadError && <p className="text-sm text-red-600 dark:text-red-400">{uploadError}</p>}

      {error && <ErrorState message={error} onRetry={load} />}
      {!error && documents === null && <SkeletonList rows={3} />}
      {!error && documents?.length === 0 && (
        <EmptyState
          title="No documents yet"
          description="Upload a PDF, DOCX, or text file to start building this project's evidence base."
        />
      )}
      {!error && documents && documents.length > 0 && (
        <ul className="flex flex-col divide-y divide-zinc-100 rounded-lg border border-zinc-200 bg-white dark:divide-zinc-800 dark:border-zinc-800 dark:bg-zinc-900">
          {documents.map((doc) => (
            <li key={doc.id} className="flex items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-50">
                  {doc.filename}
                </p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                  {formatBytes(doc.size_bytes)} · {new Date(doc.created_at).toLocaleDateString()}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STATUS_STYLES[doc.status]}`}
                >
                  {doc.status}
                </span>
                <button
                  onClick={() => handleDownload(doc)}
                  className="text-xs font-medium text-zinc-600 hover:underline dark:text-zinc-400"
                >
                  Download
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
