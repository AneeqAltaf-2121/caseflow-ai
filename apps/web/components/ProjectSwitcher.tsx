"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Project } from "@/lib/types";

export function ProjectSwitcher({ currentProject }: { currentProject: Project }) {
  const [open, setOpen] = useState(false);
  const [projects, setProjects] = useState<Project[] | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useEffect(() => {
    function onClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  async function handleOpen() {
    setOpen((v) => !v);
    if (!projects) {
      try {
        setProjects(await api.listProjects());
      } catch {
        setProjects([]);
      }
    }
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        onClick={handleOpen}
        className="flex items-center gap-2 rounded-md border border-zinc-200 px-3 py-1.5 text-sm font-medium text-zinc-900 hover:bg-zinc-50 dark:border-zinc-800 dark:text-zinc-100 dark:hover:bg-zinc-900"
      >
        <span className="max-w-[16rem] truncate">{currentProject.name}</span>
        <span aria-hidden className="text-zinc-400">
          ▾
        </span>
      </button>

      {open && (
        <div className="absolute left-0 z-10 mt-1 w-64 rounded-md border border-zinc-200 bg-white py-1 shadow-lg dark:border-zinc-800 dark:bg-zinc-950">
          {projects === null && (
            <p className="px-3 py-2 text-sm text-zinc-500">Loading…</p>
          )}
          {projects?.length === 0 && (
            <p className="px-3 py-2 text-sm text-zinc-500">No other projects.</p>
          )}
          {projects?.map((project) => (
            <Link
              key={project.id}
              href={`/projects/${project.id}`}
              onClick={() => setOpen(false)}
              className={`block truncate px-3 py-2 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-900 ${
                project.id === currentProject.id
                  ? "font-medium text-zinc-900 dark:text-zinc-50"
                  : "text-zinc-600 dark:text-zinc-400"
              }`}
            >
              {project.name}
            </Link>
          ))}
          <div className="mt-1 border-t border-zinc-200 pt-1 dark:border-zinc-800">
            <button
              onClick={() => {
                setOpen(false);
                router.push("/projects");
              }}
              className="block w-full px-3 py-2 text-left text-sm text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-900"
            >
              View all projects
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
