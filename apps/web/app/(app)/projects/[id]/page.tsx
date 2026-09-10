"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useProject } from "@/lib/hooks";
import type { CostSummary, ProjectMember, ProjectRole } from "@/lib/types";
import { ProjectSwitcher } from "@/components/ProjectSwitcher";
import { ProjectNav } from "@/components/ProjectNav";
import { ErrorState } from "@/components/ErrorState";
import { Skeleton } from "@/components/Skeleton";

export default function ProjectOverviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { project, error, loading, reload } = useProject(id);
  const router = useRouter();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const [members, setMembers] = useState<ProjectMember[] | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<ProjectRole>("viewer");
  const [inviteError, setInviteError] = useState<string | null>(null);

  const [costs, setCosts] = useState<CostSummary | null>(null);

  useEffect(() => {
    if (project) {
      setName(project.name);
      setDescription(project.description ?? "");
    }
  }, [project]);

  async function loadMembers() {
    try {
      setMembers(await api.listMembers(id));
    } catch {
      setMembers([]);
    }
  }

  useEffect(() => {
    void loadMembers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    api
      .getCostSummary(id)
      .then(setCosts)
      .catch(() => setCosts(null));
  }, [id]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSaveError(null);
    try {
      await api.updateProject(id, { name, description });
      await reload();
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Failed to save.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!confirm(`Delete "${project?.name}"? This cannot be undone.`)) return;
    try {
      await api.deleteProject(id);
      router.replace("/projects");
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Failed to delete project.");
    }
  }

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    setInviteError(null);
    try {
      await api.inviteMember(id, { email: inviteEmail.trim(), role: inviteRole });
      setInviteEmail("");
      await loadMembers();
    } catch (err) {
      setInviteError(err instanceof ApiError ? err.message : "Failed to invite member.");
    }
  }

  async function handleRemove(userId: string) {
    try {
      await api.removeMember(id, userId);
      await loadMembers();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Failed to remove member.");
    }
  }

  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (loading || !project) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <div className="flex items-center justify-between">
        <ProjectSwitcher currentProject={project} />
      </div>
      <ProjectNav projectId={id} />

      <form
        onSubmit={handleSave}
        className="flex flex-col gap-3 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
      >
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          Project details
        </h2>
        <label className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          Name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1 w-full rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950"
          />
        </label>
        <label className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          Description
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            className="mt-1 w-full rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950"
          />
        </label>
        {saveError && <p className="text-sm text-red-600 dark:text-red-400">{saveError}</p>}
        <div className="flex items-center justify-between">
          <button
            type="submit"
            disabled={saving}
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
          >
            {saving ? "Saving…" : "Save changes"}
          </button>
          <button
            type="button"
            onClick={handleDelete}
            className="text-sm font-medium text-red-600 hover:underline dark:text-red-400"
          >
            Delete project
          </button>
        </div>
      </form>

      <div className="flex flex-col gap-3 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Members</h2>

        {members === null && <Skeleton className="h-16 w-full" />}
        {members?.length === 0 && (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">No members yet.</p>
        )}
        {members && members.length > 0 && (
          <ul className="flex flex-col divide-y divide-zinc-100 dark:divide-zinc-800">
            {members.map((member) => (
              <li key={member.id} className="flex items-center justify-between py-2">
                <span className="text-sm text-zinc-700 dark:text-zinc-300">{member.user_id}</span>
                <div className="flex items-center gap-3">
                  <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium capitalize text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                    {member.role}
                  </span>
                  <button
                    onClick={() => handleRemove(member.user_id)}
                    className="text-xs font-medium text-red-600 hover:underline dark:text-red-400"
                  >
                    Remove
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}

        <form onSubmit={handleInvite} className="flex flex-wrap items-end gap-2 pt-2">
          <label className="flex-1 text-sm font-medium text-zinc-700 dark:text-zinc-300">
            Invite by email
            <input
              type="email"
              required
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="teammate@example.com"
              className="mt-1 w-full rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950"
            />
          </label>
          <label className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
            Role
            <select
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value as ProjectRole)}
              className="mt-1 rounded-md border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-950"
            >
              <option value="viewer">Viewer</option>
              <option value="editor">Editor</option>
              <option value="owner">Owner</option>
            </select>
          </label>
          <button
            type="submit"
            className="rounded-md border border-zinc-300 px-3 py-2 text-sm font-medium hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            Invite
          </button>
        </form>
        {inviteError && <p className="text-sm text-red-600 dark:text-red-400">{inviteError}</p>}
        <p className="text-xs text-zinc-400">
          The invitee must already have a CaseFlow account (signed in at least once).
        </p>
      </div>

      <div className="flex flex-col gap-3 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          Cost (Phase 32)
        </h2>
        {costs === null && (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">No LLM spend recorded yet.</p>
        )}
        {costs && (
          <div className="flex flex-wrap gap-4">
            <div>
              <p className="text-[11px] font-medium text-zinc-500 dark:text-zinc-400">
                Total spend
              </p>
              <p className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
                {costs.total_cost_usd < 0.01
                  ? `$${costs.total_cost_usd.toFixed(4)}`
                  : `$${costs.total_cost_usd.toFixed(2)}`}
              </p>
            </div>
            <div>
              <p className="text-[11px] font-medium text-zinc-500 dark:text-zinc-400">
                Model calls
              </p>
              <p className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
                {costs.total_runs}
              </p>
            </div>
            <div>
              <p className="text-[11px] font-medium text-zinc-500 dark:text-zinc-400">
                Tokens (in / out)
              </p>
              <p className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
                {costs.total_input_tokens} / {costs.total_output_tokens}
              </p>
            </div>
            {Object.keys(costs.by_model).length > 0 && (
              <div className="w-full">
                <p className="text-[11px] font-medium text-zinc-500 dark:text-zinc-400">
                  By model
                </p>
                <ul className="mt-1 flex flex-col gap-0.5 text-sm text-zinc-700 dark:text-zinc-300">
                  {Object.entries(costs.by_model).map(([model, cost]) => (
                    <li key={model} className="flex justify-between gap-3">
                      <span>{model}</span>
                      <span className="font-medium">
                        {cost < 0.01 ? `$${cost.toFixed(4)}` : `$${cost.toFixed(2)}`}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
