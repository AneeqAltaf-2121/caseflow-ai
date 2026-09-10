"use client";

import { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useProject } from "@/lib/hooks";
import type { Report, ReportDetail, ReportType } from "@/lib/types";
import { ProjectSwitcher } from "@/components/ProjectSwitcher";
import { ProjectNav } from "@/components/ProjectNav";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { Skeleton, SkeletonList } from "@/components/Skeleton";

const REPORT_TYPES: { value: ReportType; label: string }[] = [
  { value: "executive_summary", label: "Executive Summary" },
  { value: "evidence_report", label: "Evidence Report" },
  { value: "risk_analysis", label: "Risk Analysis" },
  { value: "chronology", label: "Chronology" },
  { value: "contradiction_report", label: "Contradiction Report" },
  { value: "research_memo", label: "Research Memo" },
];

const STATUS_STYLES: Record<Report["status"], string> = {
  queued: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300",
  processing: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  ready: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
};

export default function ReportsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { project, error: projectError } = useProject(id);

  const [reports, setReports] = useState<Report[] | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ReportDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [reportType, setReportType] = useState<ReportType>("executive_summary");
  const [title, setTitle] = useState("");
  const [creating, setCreating] = useState(false);

  async function loadReports() {
    try {
      setReports(await api.listReports(id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load reports.");
    }
  }

  useEffect(() => {
    void loadReports();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const statusRef = useRef<ReportDetail["status"] | null>(null);

  async function loadDetail(reportId: string) {
    try {
      const fetched = await api.getReport(id, reportId);
      setDetail(fetched);
      statusRef.current = fetched.status;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load report.");
    }
  }

  useEffect(() => {
    if (!activeId) return;
    statusRef.current = null;
    void loadDetail(activeId);
    // Poll while a report is still being generated in the background;
    // stops itself once the status settles rather than polling forever.
    const interval = setInterval(() => {
      if (statusRef.current === "ready" || statusRef.current === "failed") {
        clearInterval(interval);
        return;
      }
      void loadDetail(activeId).then(() => void loadReports());
    }, 3000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const report = await api.createReport(id, reportType, title.trim());
      setTitle("");
      setShowCreate(false);
      await loadReports();
      setActiveId(report.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create report.");
    } finally {
      setCreating(false);
    }
  }

  if (projectError) return <ErrorState message={projectError} />;
  if (!project) return <Skeleton className="h-40 w-full" />;

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
            {showCreate ? "Cancel" : "New report"}
          </button>

          {showCreate && (
            <form
              onSubmit={handleCreate}
              className="flex flex-col gap-2 rounded-md border border-zinc-200 p-3 dark:border-zinc-800"
            >
              <select
                value={reportType}
                onChange={(e) => setReportType(e.target.value as ReportType)}
                className="rounded-md border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
              >
                {REPORT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Report title"
                className="rounded-md border border-zinc-300 px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
              />
              <button
                type="submit"
                disabled={creating}
                className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
              >
                {creating ? "Starting…" : "Generate"}
              </button>
            </form>
          )}

          {reports === null && <SkeletonList rows={3} />}
          {reports?.length === 0 && (
            <p className="px-1 text-xs text-zinc-400">No reports yet.</p>
          )}
          <ul className="flex flex-col gap-1">
            {reports?.map((report) => (
              <li key={report.id}>
                <button
                  onClick={() => setActiveId(report.id)}
                  className={`flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm ${
                    activeId === report.id
                      ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                      : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"
                  }`}
                >
                  <span className="min-w-0 flex-1 truncate">{report.title}</span>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium capitalize ${STATUS_STYLES[report.status]}`}
                  >
                    {report.status}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col gap-4">
          {!activeId && (
            <EmptyState
              title="Generate a report"
              description="Executive summaries, evidence reports, risk analyses, chronologies, contradiction reports, and research memos — each section is grounded with its own citations, generated in the background."
            />
          )}

          {activeId && !detail && <Skeleton className="h-40 w-full" />}

          {activeId && detail && (
            <div className="flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
                  {detail.title}
                </h2>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STATUS_STYLES[detail.status]}`}
                >
                  {detail.status}
                </span>
              </div>

              {detail.status === "queued" || detail.status === "processing" ? (
                <EmptyState
                  title="Generating…"
                  description="This report is being written in the background. This page updates automatically."
                />
              ) : detail.status === "failed" ? (
                <ErrorState message={detail.error ?? "Report generation failed."} />
              ) : (
                <div className="flex flex-col gap-6">
                  {detail.sections.map((section) => (
                    <div key={section.id}>
                      <h3 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                        {section.heading}
                      </h3>
                      <p className="whitespace-pre-wrap text-sm text-zinc-700 dark:text-zinc-300">
                        {section.content}
                      </p>
                      {section.citations.length > 0 && (
                        <div className="mt-3 flex flex-col gap-2 border-t border-zinc-100 pt-3 dark:border-zinc-800">
                          <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                            Sources
                          </p>
                          {section.citations.map((citation) => (
                            <Link
                              key={citation.id}
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
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
