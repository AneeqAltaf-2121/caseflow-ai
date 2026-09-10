"use client";

import { use, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useProject } from "@/lib/hooks";
import type { EvaluationResult, EvaluationRun, EvaluationRunDetail } from "@/lib/types";
import { ProjectSwitcher } from "@/components/ProjectSwitcher";
import { ProjectNav } from "@/components/ProjectNav";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { Skeleton, SkeletonList } from "@/components/Skeleton";

const STATUS_STYLES: Record<EvaluationRun["status"], string> = {
  queued: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300",
  running: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  succeeded: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
};

function mean(values: number[]): number | null {
  if (values.length === 0) return null;
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

function pct(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(0)}%`;
}

function usd(value: number): string {
  return value < 0.01 ? `$${value.toFixed(4)}` : `$${value.toFixed(2)}`;
}

interface RunMetrics {
  faithfulness: number | null;
  relevance: number | null;
  completeness: number | null;
  recall: number | null;
  citationAccuracy: number | null;
  hallucinationRate: number | null;
  latencyP50: number | null;
  latencyP95: number | null;
  totalCost: number;
}

function percentile(sorted: number[], p: number): number | null {
  if (sorted.length === 0) return null;
  const index = Math.min(sorted.length - 1, Math.floor(p * sorted.length));
  return sorted[index];
}

function computeMetrics(results: EvaluationResult[]): RunMetrics {
  const latencies = [...results.map((r) => r.latency_ms)].sort((a, b) => a - b);
  const recallValues = results
    .map((r) => r.recall_at_k)
    .filter((v): v is number => v !== null);
  const citationChecks = results.length;
  const citationCorrectCount = results.filter((r) => r.citation_correct).length;
  const hallucinated = results.filter(
    (r) => r.faithfulness_score !== null && r.faithfulness_score < 0.5
  ).length;

  return {
    faithfulness: mean(
      results.map((r) => r.faithfulness_score).filter((v): v is number => v !== null)
    ),
    relevance: mean(results.map((r) => r.relevance_score).filter((v): v is number => v !== null)),
    completeness: mean(
      results.map((r) => r.completeness_score).filter((v): v is number => v !== null)
    ),
    recall: recallValues.length > 0 ? mean(recallValues) : null,
    citationAccuracy: citationChecks > 0 ? citationCorrectCount / citationChecks : null,
    hallucinationRate: results.length > 0 ? hallucinated / results.length : null,
    latencyP50: percentile(latencies, 0.5),
    latencyP95: percentile(latencies, 0.95),
    totalCost: results.reduce((sum, r) => sum + r.cost_usd, 0),
  };
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-zinc-200 px-3 py-2 dark:border-zinc-800">
      <p className="text-[11px] font-medium text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className="mt-0.5 text-lg font-semibold text-zinc-900 dark:text-zinc-50">{value}</p>
    </div>
  );
}

export default function EvaluationsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { project, error: projectError } = useProject(id);

  const [runs, setRuns] = useState<EvaluationRun[] | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EvaluationRunDetail | null>(null);
  const [expandedResultId, setExpandedResultId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [datasetName, setDatasetName] = useState("sample_contract_qa");
  const [creating, setCreating] = useState(false);

  async function loadRuns() {
    try {
      setRuns(await api.listEvaluationRuns(id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load evaluation runs.");
    }
  }

  useEffect(() => {
    void loadRuns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const statusRef = useRef<EvaluationRunDetail["status"] | null>(null);

  async function loadDetail(evaluationRunId: string) {
    try {
      const fetched = await api.getEvaluationRun(id, evaluationRunId);
      setDetail(fetched);
      statusRef.current = fetched.status;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load evaluation run.");
    }
  }

  useEffect(() => {
    if (!activeId) return;
    statusRef.current = null;
    setExpandedResultId(null);
    void loadDetail(activeId);
    // Poll while a run is still grading in the background; stops itself
    // once the status settles rather than polling forever.
    const interval = setInterval(() => {
      if (statusRef.current === "succeeded" || statusRef.current === "failed") {
        clearInterval(interval);
        return;
      }
      void loadDetail(activeId).then(() => void loadRuns());
    }, 3000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!datasetName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const run = await api.createEvaluationRun(id, datasetName.trim());
      setShowCreate(false);
      await loadRuns();
      setActiveId(run.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to start evaluation run.");
    } finally {
      setCreating(false);
    }
  }

  if (projectError) return <ErrorState message={projectError} />;
  if (!project) return <Skeleton className="h-40 w-full" />;

  const metrics = detail ? computeMetrics(detail.results) : null;

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <ProjectSwitcher currentProject={project} />
      <ProjectNav projectId={id} />

      {error && <ErrorState message={error} />}

      <div className="flex gap-6">
        <aside className="flex w-64 shrink-0 flex-col gap-2">
          <button
            onClick={() => setShowCreate((v) => !v)}
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900"
          >
            {showCreate ? "Cancel" : "New evaluation run"}
          </button>

          {showCreate && (
            <form
              onSubmit={handleCreate}
              className="flex flex-col gap-2 rounded-md border border-zinc-200 p-3 dark:border-zinc-800"
            >
              <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                Dataset name
              </label>
              <input
                value={datasetName}
                onChange={(e) => setDatasetName(e.target.value)}
                placeholder="sample_contract_qa"
                className="rounded-md border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
              />
              <p className="text-[11px] text-zinc-400">
                Matches a file in packages/evals/datasets — see docs/evaluations.md.
              </p>
              <button
                type="submit"
                disabled={creating}
                className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
              >
                {creating ? "Starting…" : "Run evaluation"}
              </button>
            </form>
          )}

          {runs === null && <SkeletonList rows={3} />}
          {runs?.length === 0 && <p className="px-1 text-xs text-zinc-400">No runs yet.</p>}
          <ul className="flex flex-col gap-1">
            {runs?.map((run) => (
              <li key={run.id}>
                <button
                  onClick={() => setActiveId(run.id)}
                  className={`flex w-full flex-col gap-0.5 rounded-md px-2 py-1.5 text-left text-sm ${
                    activeId === run.id
                      ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                      : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"
                  }`}
                >
                  <span className="flex w-full items-center justify-between gap-2">
                    <span className="min-w-0 flex-1 truncate">{run.dataset_name}</span>
                    <span
                      className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium capitalize ${STATUS_STYLES[run.status]}`}
                    >
                      {run.status}
                    </span>
                  </span>
                  <span
                    className={`text-[11px] ${activeId === run.id ? "opacity-80" : "text-zinc-400"}`}
                  >
                    v{run.dataset_version} · {run.model}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col gap-4">
          {!activeId && (
            <EmptyState
              title="Evaluate answer quality"
              description="Run a dataset (see packages/evals/datasets) through this project's retriever and RAG pipeline to measure faithfulness, relevance, completeness, citation accuracy, hallucination rate, recall, latency, and cost."
            />
          )}

          {activeId && !detail && <Skeleton className="h-40 w-full" />}

          {activeId && detail && (
            <div className="flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
                    {detail.dataset_name}{" "}
                    <span className="text-sm font-normal text-zinc-400">
                      v{detail.dataset_version}
                    </span>
                  </h2>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {detail.model} · retriever {detail.retriever_version}
                  </p>
                </div>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STATUS_STYLES[detail.status]}`}
                >
                  {detail.status}
                </span>
              </div>

              {detail.status === "queued" || detail.status === "running" ? (
                <EmptyState
                  title="Grading…"
                  description="This evaluation run is grading each example in the background. This page updates automatically."
                />
              ) : detail.status === "failed" ? (
                <ErrorState message={detail.error ?? "Evaluation run failed."} />
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    <MetricCard label="Faithfulness" value={pct(metrics!.faithfulness)} />
                    <MetricCard label="Relevance" value={pct(metrics!.relevance)} />
                    <MetricCard label="Completeness" value={pct(metrics!.completeness)} />
                    <MetricCard label="Recall@K" value={pct(metrics!.recall)} />
                    <MetricCard
                      label="Citation accuracy"
                      value={pct(metrics!.citationAccuracy)}
                    />
                    <MetricCard
                      label="Hallucination rate"
                      value={pct(metrics!.hallucinationRate)}
                    />
                    <MetricCard
                      label="Latency P50 / P95"
                      value={
                        metrics!.latencyP50 === null
                          ? "—"
                          : `${metrics!.latencyP50}ms / ${metrics!.latencyP95}ms`
                      }
                    />
                    <MetricCard label="Total cost" value={usd(metrics!.totalCost)} />
                  </div>

                  <div className="flex flex-col gap-2">
                    <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                      Examples ({detail.results.length})
                    </h3>
                    {detail.results.map((result) => {
                      const expanded = expandedResultId === result.id;
                      return (
                        <div
                          key={result.id}
                          className="rounded-md border border-zinc-200 dark:border-zinc-800"
                        >
                          <button
                            onClick={() => setExpandedResultId(expanded ? null : result.id)}
                            className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left"
                          >
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-sm text-zinc-800 dark:text-zinc-200">
                                {result.question}
                              </p>
                              <p className="text-[11px] text-zinc-400">{result.example_id}</p>
                            </div>
                            <div className="flex shrink-0 items-center gap-2 text-[11px]">
                              <span
                                className={
                                  result.citation_correct
                                    ? "text-emerald-600 dark:text-emerald-400"
                                    : "text-red-600 dark:text-red-400"
                                }
                              >
                                {result.citation_correct ? "citations ok" : "citation issue"}
                              </span>
                              <span className="text-zinc-400">
                                F {pct(result.faithfulness_score)}
                              </span>
                              <span className="text-zinc-400">{result.latency_ms}ms</span>
                            </div>
                          </button>
                          {expanded && (
                            <div className="flex flex-col gap-3 border-t border-zinc-100 px-3 py-3 text-sm dark:border-zinc-800">
                              <div>
                                <p className="text-[11px] font-medium text-zinc-500 dark:text-zinc-400">
                                  Generated answer
                                </p>
                                <p className="whitespace-pre-wrap text-zinc-700 dark:text-zinc-300">
                                  {result.generated_answer}
                                </p>
                              </div>
                              {result.expected_answer && (
                                <div>
                                  <p className="text-[11px] font-medium text-zinc-500 dark:text-zinc-400">
                                    Expected answer
                                  </p>
                                  <p className="whitespace-pre-wrap text-zinc-700 dark:text-zinc-300">
                                    {result.expected_answer}
                                  </p>
                                </div>
                              )}
                              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                                <MetricCard
                                  label="Faithfulness"
                                  value={pct(result.faithfulness_score)}
                                />
                                <MetricCard label="Relevance" value={pct(result.relevance_score)} />
                                <MetricCard
                                  label="Completeness"
                                  value={pct(result.completeness_score)}
                                />
                                <MetricCard
                                  label="Citation support"
                                  value={pct(result.citation_support_score)}
                                />
                                <MetricCard label="Recall@K" value={pct(result.recall_at_k)} />
                                <MetricCard
                                  label="Precision@K"
                                  value={pct(result.precision_at_k)}
                                />
                                <MetricCard label="MRR" value={pct(result.mrr)} />
                                <MetricCard label="Cost" value={usd(result.cost_usd)} />
                              </div>
                              {result.judge_reason && (
                                <p className="text-xs text-zinc-500 dark:text-zinc-400">
                                  Judge: {result.judge_reason}
                                </p>
                              )}
                              {result.grader_details.deterministic_failures.length > 0 && (
                                <ul className="list-disc pl-4 text-xs text-red-600 dark:text-red-400">
                                  {result.grader_details.deterministic_failures.map((f) => (
                                    <li key={f}>{f}</li>
                                  ))}
                                </ul>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
