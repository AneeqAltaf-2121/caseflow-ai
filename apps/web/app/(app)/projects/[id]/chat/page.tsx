"use client";

import { use } from "react";
import { useProject } from "@/lib/hooks";
import { ProjectSwitcher } from "@/components/ProjectSwitcher";
import { ProjectNav } from "@/components/ProjectNav";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { Skeleton } from "@/components/Skeleton";

export default function ChatPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { project, error } = useProject(id);

  if (error) return <ErrorState message={error} />;
  if (!project) return <Skeleton className="h-40 w-full" />;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <ProjectSwitcher currentProject={project} />
      <ProjectNav projectId={id} />

      <EmptyState
        title="Citation-grounded chat is coming soon"
        description="Once documents in this project are ingested and embedded, you'll be able to ask questions here and get answers grounded in your uploaded evidence, with clickable citations back to source passages."
      />
    </div>
  );
}
