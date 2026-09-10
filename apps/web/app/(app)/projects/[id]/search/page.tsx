"use client";

import { use, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useProject } from "@/lib/hooks";
import type { HybridSearchResult, SearchResult } from "@/lib/types";
import { ProjectSwitcher } from "@/components/ProjectSwitcher";
import { ProjectNav } from "@/components/ProjectNav";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { Skeleton, SkeletonList } from "@/components/Skeleton";

type Mode = "semantic" | "keyword" | "hybrid" | "rerank";

const MODES: { value: Mode; label: string; description: string }[] = [
  { value: "semantic", label: "Semantic", description: "Vector similarity — meaning, not exact words." },
  { value: "keyword", label: "Keyword", description: "BM25 — exact terms and terminology." },
  { value: "hybrid", label: "Hybrid", description: "Both, combined by reciprocal rank fusion." },
  { value: "rerank", label: "Reranked", description: "Hybrid's top results, narrowed by phrase-match reranking." },
];

export default function SearchPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { project, error: projectError } = useProject(id);

  const [mode, setMode] = useState<Mode>("hybrid");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<(SearchResult | HybridSearchResult)[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    setHasSearched(true);
    try {
      const trimmed = query.trim();
      if (mode === "semantic") setResults(await api.semanticSearch(id, trimmed));
      else if (mode === "keyword") setResults(await api.keywordSearch(id, trimmed));
      else if (mode === "hybrid") setResults(await api.hybridSearch(id, trimmed));
      else setResults(await api.rerankSearch(id, trimmed));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed.");
      setResults(null);
    } finally {
      setSearching(false);
    }
  }

  if (projectError) return <ErrorState message={projectError} />;
  if (!project) return <Skeleton className="h-40 w-full" />;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <ProjectSwitcher currentProject={project} />
      <ProjectNav projectId={id} />

      <div className="flex flex-wrap gap-2">
        {MODES.map((m) => (
          <button
            key={m.value}
            type="button"
            onClick={() => setMode(m.value)}
            title={m.description}
            className={`rounded-full px-3 py-1 text-xs font-medium ${
              mode === m.value
                ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      <form onSubmit={handleSearch} className="flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search this project's documents…"
          className="flex-1 rounded-md border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-950"
        />
        <button
          type="submit"
          disabled={searching}
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {searching ? "Searching…" : "Search"}
        </button>
      </form>

      {error && <ErrorState message={error} />}
      {searching && <SkeletonList rows={3} />}
      {!searching && !error && hasSearched && results?.length === 0 && (
        <EmptyState
          title="No matching passages"
          description="Try different words, another mode, or upload more documents to this project."
        />
      )}
      {!searching && !error && results && results.length > 0 && (
        <ul className="flex flex-col gap-3">
          {results.map((result) => (
            <li
              key={result.chunk_id}
              className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
            >
              <div className="mb-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs text-zinc-500 dark:text-zinc-400">
                <Link
                  href={`/projects/${id}/documents`}
                  className="font-medium text-zinc-700 hover:underline dark:text-zinc-300"
                >
                  {result.document_filename}
                </Link>
                {"fused_score" in result ? (
                  <span>
                    page {result.page_number} · fused {result.fused_score.toFixed(4)}
                    {result.vector_rank !== null && ` · vector #${result.vector_rank}`}
                    {result.keyword_rank !== null && ` · keyword #${result.keyword_rank}`}
                  </span>
                ) : (
                  <span>
                    page {result.page_number} · score {result.score.toFixed(2)}
                  </span>
                )}
              </div>
              <p className="whitespace-pre-wrap text-sm text-zinc-700 dark:text-zinc-300">
                {result.text}
              </p>
            </li>
          ))}
        </ul>
      )}
      {!hasSearched && !error && (
        <EmptyState
          title="Search across this project's documents"
          description="Semantic search finds passages by meaning; keyword search finds exact terms; hybrid combines both."
        />
      )}
    </div>
  );
}
