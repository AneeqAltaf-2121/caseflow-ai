"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { Project } from "@/lib/types";
import { SkeletonList } from "@/components/Skeleton";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";

export default function DashboardPage() {
  const { user } = useAuth();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    setProjects(null);
    try {
      setProjects(await api.listProjects());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load projects.");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">
          Welcome back{user ? `, ${user.display_name}` : ""}
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Here&apos;s what&apos;s happening across your projects.
        </p>
      </div>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
            Recent projects
          </h2>
          <Link
            href="/projects"
            className="text-sm font-medium text-zinc-600 hover:underline dark:text-zinc-400"
          >
            View all
          </Link>
        </div>

        {error && <ErrorState message={error} onRetry={load} />}
        {!error && projects === null && <SkeletonList rows={3} />}
        {!error && projects?.length === 0 && (
          <EmptyState
            title="No projects yet"
            description="Create your first project to start uploading documents."
            action={
              <Link
                href="/projects"
                className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900"
              >
                Create a project
              </Link>
            }
          />
        )}
        {!error && projects && projects.length > 0 && (
          <ul className="flex flex-col gap-2">
            {projects.slice(0, 5).map((project) => (
              <li key={project.id}>
                <Link
                  href={`/projects/${project.id}`}
                  className="block rounded-lg border border-zinc-200 bg-white px-4 py-3 hover:border-zinc-300 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-zinc-700"
                >
                  <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">
                    {project.name}
                  </p>
                  {project.description && (
                    <p className="mt-0.5 truncate text-sm text-zinc-500 dark:text-zinc-400">
                      {project.description}
                    </p>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
