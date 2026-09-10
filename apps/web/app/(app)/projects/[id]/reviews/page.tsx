"use client";

import { use, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useProject } from "@/lib/hooks";
import type { HumanReview, HumanReviewStatus } from "@/lib/types";
import { ProjectSwitcher } from "@/components/ProjectSwitcher";
import { ProjectNav } from "@/components/ProjectNav";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { Skeleton, SkeletonList } from "@/components/Skeleton";

const STATUS_STYLES: Record<HumanReviewStatus, string> = {
  needs_review: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  approved: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  rejected: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
  corrected: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
};

const FILTERS: { value: HumanReviewStatus | "all"; label: string }[] = [
  { value: "needs_review", label: "Needs review" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "corrected", label: "Corrected" },
  { value: "all", label: "All" },
];

export default function ReviewsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { project, error: projectError } = useProject(id);

  const [filter, setFilter] = useState<HumanReviewStatus | "all">("needs_review");
  const [reviews, setReviews] = useState<HumanReview[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [correctedAnswer, setCorrectedAnswer] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function loadReviews() {
    try {
      setReviews(await api.listReviews(id, filter === "all" ? undefined : filter));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load reviews.");
    }
  }

  useEffect(() => {
    setReviews(null);
    void loadReviews();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, filter]);

  const active = reviews?.find((r) => r.id === activeId) ?? null;

  async function handleDecision(status: HumanReviewStatus) {
    if (!active) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.submitReviewDecision(id, active.id, {
        status,
        corrected_answer: status === "corrected" ? correctedAnswer.trim() : undefined,
        reason: reason.trim() || undefined,
      });
      setActiveId(null);
      setReason("");
      setCorrectedAnswer("");
      await loadReviews();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to submit decision.");
    } finally {
      setSubmitting(false);
    }
  }

  if (projectError) return <ErrorState message={projectError} />;
  if (!project) return <Skeleton className="h-40 w-full" />;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <ProjectSwitcher currentProject={project} />
      <ProjectNav projectId={id} />

      {error && <ErrorState message={error} />}

      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`rounded-full px-3 py-1 text-xs font-medium ${
              filter === f.value
                ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {reviews === null && <SkeletonList rows={3} />}
      {reviews?.length === 0 && (
        <EmptyState
          title="No reviews here"
          description="Flag a generated chat answer for review from the Chat tab — low-confidence or questionable answers show up here for an owner or editor to approve, reject, or correct."
        />
      )}

      <div className="flex flex-col gap-3">
        {reviews?.map((review) => {
          const isOpen = activeId === review.id;
          return (
            <div
              key={review.id}
              className="rounded-md border border-zinc-200 dark:border-zinc-800"
            >
              <button
                onClick={() => setActiveId(isOpen ? null : review.id)}
                className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left"
              >
                <p className="min-w-0 flex-1 truncate text-sm text-zinc-800 dark:text-zinc-200">
                  {review.original_answer}
                </p>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium capitalize ${STATUS_STYLES[review.status]}`}
                >
                  {review.status.replace("_", " ")}
                </span>
              </button>

              {isOpen && (
                <div className="flex flex-col gap-3 border-t border-zinc-100 px-3 py-3 dark:border-zinc-800">
                  <div>
                    <p className="text-[11px] font-medium text-zinc-500 dark:text-zinc-400">
                      Original answer
                    </p>
                    <p className="whitespace-pre-wrap text-sm text-zinc-700 dark:text-zinc-300">
                      {review.original_answer}
                    </p>
                  </div>

                  {review.status === "needs_review" ? (
                    <>
                      <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        Reason (optional)
                        <textarea
                          value={reason}
                          onChange={(e) => setReason(e.target.value)}
                          rows={2}
                          className="mt-1 w-full rounded-md border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
                        />
                      </label>
                      <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        Corrected answer (only used for &quot;Correct&quot;)
                        <textarea
                          value={correctedAnswer}
                          onChange={(e) => setCorrectedAnswer(e.target.value)}
                          rows={3}
                          className="mt-1 w-full rounded-md border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
                        />
                      </label>
                      <div className="flex gap-2">
                        <button
                          disabled={submitting}
                          onClick={() => handleDecision("approved")}
                          className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                        >
                          Approve
                        </button>
                        <button
                          disabled={submitting}
                          onClick={() => handleDecision("rejected")}
                          className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
                        >
                          Reject
                        </button>
                        <button
                          disabled={submitting || !correctedAnswer.trim()}
                          onClick={() => handleDecision("corrected")}
                          className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
                        >
                          Correct
                        </button>
                      </div>
                    </>
                  ) : (
                    <div className="flex flex-col gap-1 text-xs text-zinc-500 dark:text-zinc-400">
                      {review.corrected_answer && (
                        <p>
                          <span className="font-medium">Corrected answer:</span>{" "}
                          {review.corrected_answer}
                        </p>
                      )}
                      {review.reason && (
                        <p>
                          <span className="font-medium">Reason:</span> {review.reason}
                        </p>
                      )}
                      <p>Reviewed {review.reviewed_at}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
