"use client";

import { use, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useProject } from "@/lib/hooks";
import type { AskAnswer } from "@/lib/types";
import { ProjectSwitcher } from "@/components/ProjectSwitcher";
import { ProjectNav } from "@/components/ProjectNav";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { Skeleton } from "@/components/Skeleton";

interface Turn {
  question: string;
  answer: AskAnswer;
}

export default function ChatPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { project, error: projectError } = useProject(id);

  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = question.trim();
    if (!trimmed) return;
    setAsking(true);
    setError(null);
    try {
      const answer = await api.ask(id, trimmed);
      setTurns((prev) => [...prev, { question: trimmed, answer }]);
      setQuestion("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to get an answer.");
    } finally {
      setAsking(false);
    }
  }

  if (projectError) return <ErrorState message={projectError} />;
  if (!project) return <Skeleton className="h-40 w-full" />;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <ProjectSwitcher currentProject={project} />
      <ProjectNav projectId={id} />

      {turns.length === 0 && !asking && (
        <EmptyState
          title="Ask a question about this project's documents"
          description="Answers are grounded in your uploaded evidence, with numbered citations back to the source page."
        />
      )}

      <div className="flex flex-col gap-4">
        {turns.map((turn, i) => (
          <div key={i} className="flex flex-col gap-2">
            <p className="self-end rounded-lg bg-zinc-900 px-4 py-2 text-sm text-white dark:bg-zinc-100 dark:text-zinc-900">
              {turn.question}
            </p>
            <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
              <p className="whitespace-pre-wrap text-sm text-zinc-800 dark:text-zinc-200">
                {turn.answer.answer}
              </p>
              {turn.answer.citations.length > 0 && (
                <div className="mt-3 flex flex-col gap-2 border-t border-zinc-100 pt-3 dark:border-zinc-800">
                  <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Sources</p>
                  {turn.answer.citations.map((citation) => (
                    <Link
                      key={citation.document_chunk_id}
                      href={`/projects/${id}/documents`}
                      className="rounded-md border border-zinc-200 px-3 py-2 text-xs hover:border-zinc-400 dark:border-zinc-700 dark:hover:border-zinc-500"
                    >
                      <span className="font-medium text-zinc-700 dark:text-zinc-300">
                        [{citation.source_number}] {citation.document_filename} · page{" "}
                        {citation.page_number}
                      </span>
                      <p className="mt-1 truncate text-zinc-500 dark:text-zinc-400">
                        {citation.quote}
                      </p>
                    </Link>
                  ))}
                </div>
              )}
              {turn.answer.sources_considered === 0 && (
                <p className="mt-2 text-xs italic text-zinc-400">
                  No documents were found to answer this question.
                </p>
              )}
            </div>
          </div>
        ))}
        {asking && (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-8 w-2/3 self-end" />
            <Skeleton className="h-20 w-full" />
          </div>
        )}
      </div>

      {error && <ErrorState message={error} />}

      <form onSubmit={handleAsk} className="flex gap-2">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question…"
          className="flex-1 rounded-md border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-950"
        />
        <button
          type="submit"
          disabled={asking}
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {asking ? "Thinking…" : "Ask"}
        </button>
      </form>
    </div>
  );
}
