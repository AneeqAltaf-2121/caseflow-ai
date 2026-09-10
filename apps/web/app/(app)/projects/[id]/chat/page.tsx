"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useProject } from "@/lib/hooks";
import type { Conversation, ConversationDetail } from "@/lib/types";
import { ProjectSwitcher } from "@/components/ProjectSwitcher";
import { ProjectNav } from "@/components/ProjectNav";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { Skeleton, SkeletonList } from "@/components/Skeleton";

export default function ChatPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { project, error: projectError } = useProject(id);

  const [conversations, setConversations] = useState<Conversation[] | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [flaggedIds, setFlaggedIds] = useState<Set<string>>(new Set());

  async function loadConversations() {
    try {
      const list = await api.listConversations(id);
      setConversations(list);
      return list;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load conversations.");
      return [];
    }
  }

  useEffect(() => {
    void loadConversations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function loadDetail(conversationId: string) {
    setDetailLoading(true);
    try {
      setDetail(await api.getConversation(id, conversationId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load conversation.");
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleSelect(conversationId: string) {
    setActiveId(conversationId);
    await loadDetail(conversationId);
  }

  async function handleNewConversation() {
    setError(null);
    try {
      const conversation = await api.createConversation(id);
      setConversations((prev) => [conversation, ...(prev ?? [])]);
      await handleSelect(conversation.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create conversation.");
    }
  }

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || !activeId) return;
    setAsking(true);
    setError(null);
    try {
      await api.postMessage(id, activeId, trimmed);
      setQuestion("");
      await loadDetail(activeId);
      await loadConversations();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to get an answer.");
    } finally {
      setAsking(false);
    }
  }

  async function handleRename(conversationId: string) {
    const title = renameValue.trim();
    if (!title) {
      setRenamingId(null);
      return;
    }
    try {
      await api.renameConversation(id, conversationId, title);
      setRenamingId(null);
      await loadConversations();
      if (activeId === conversationId) await loadDetail(conversationId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to rename conversation.");
    }
  }

  async function handleFlag(messageId: string) {
    try {
      await api.flagMessageForReview(id, messageId);
      setFlaggedIds((prev) => new Set(prev).add(messageId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to flag this answer for review.");
    }
  }

  async function handleDelete(conversationId: string) {
    if (!confirm("Delete this conversation?")) return;
    try {
      await api.deleteConversation(id, conversationId);
      if (activeId === conversationId) {
        setActiveId(null);
        setDetail(null);
      }
      await loadConversations();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete conversation.");
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
        <aside className="flex w-56 shrink-0 flex-col gap-2">
          <button
            onClick={handleNewConversation}
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900"
          >
            New chat
          </button>
          {conversations === null && <SkeletonList rows={3} />}
          {conversations?.length === 0 && (
            <p className="px-1 text-xs text-zinc-400">No conversations yet.</p>
          )}
          <ul className="flex flex-col gap-1">
            {conversations?.map((conversation) => (
              <li key={conversation.id}>
                {renamingId === conversation.id ? (
                  <input
                    autoFocus
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onBlur={() => handleRename(conversation.id)}
                    onKeyDown={(e) => e.key === "Enter" && handleRename(conversation.id)}
                    className="w-full rounded-md border border-zinc-300 px-2 py-1 text-sm dark:border-zinc-700 dark:bg-zinc-950"
                  />
                ) : (
                  <div
                    className={`group flex items-center justify-between rounded-md px-2 py-1.5 text-sm ${
                      activeId === conversation.id
                        ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                        : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"
                    }`}
                  >
                    <button
                      onClick={() => handleSelect(conversation.id)}
                      className="min-w-0 flex-1 truncate text-left"
                    >
                      {conversation.title}
                    </button>
                    <span className="hidden gap-1 group-hover:flex">
                      <button
                        onClick={() => {
                          setRenamingId(conversation.id);
                          setRenameValue(conversation.title);
                        }}
                        className="text-xs opacity-70 hover:opacity-100"
                        aria-label="Rename"
                      >
                        ✎
                      </button>
                      <button
                        onClick={() => handleDelete(conversation.id)}
                        className="text-xs opacity-70 hover:opacity-100"
                        aria-label="Delete"
                      >
                        ✕
                      </button>
                    </span>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col gap-4">
          {!activeId && (
            <EmptyState
              title="Select or start a conversation"
              description="Answers are grounded in your uploaded evidence, with numbered citations back to the source page."
            />
          )}

          {activeId && detailLoading && (
            <div className="flex flex-col gap-2">
              <Skeleton className="h-8 w-2/3 self-end" />
              <Skeleton className="h-20 w-full" />
            </div>
          )}

          {activeId && !detailLoading && detail && (
            <>
              <div className="flex flex-col gap-4">
                {detail.messages.map((message) =>
                  message.role === "user" ? (
                    <p
                      key={message.id}
                      className="self-end rounded-lg bg-zinc-900 px-4 py-2 text-sm text-white dark:bg-zinc-100 dark:text-zinc-900"
                    >
                      {message.content}
                    </p>
                  ) : (
                    <div
                      key={message.id}
                      className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
                    >
                      {message.citations.length === 0 && (
                        <p className="mb-2 rounded-md bg-amber-50 px-2 py-1 text-xs font-medium text-amber-700 dark:bg-amber-950 dark:text-amber-300">
                          ⚠ This answer cited no sources — treat it as unverified.
                        </p>
                      )}
                      <p className="whitespace-pre-wrap text-sm text-zinc-800 dark:text-zinc-200">
                        {message.content}
                      </p>
                      <button
                        onClick={() => handleFlag(message.id)}
                        disabled={flaggedIds.has(message.id)}
                        className="mt-2 text-xs font-medium text-zinc-400 hover:text-zinc-700 disabled:text-emerald-600 dark:hover:text-zinc-200 dark:disabled:text-emerald-400"
                      >
                        {flaggedIds.has(message.id) ? "✓ Flagged for review" : "Flag for review"}
                      </button>
                      {message.citations.length > 0 && (
                        <div className="mt-3 flex flex-col gap-2 border-t border-zinc-100 pt-3 dark:border-zinc-800">
                          <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                            Sources
                          </p>
                          {message.citations.map((citation) => (
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
                  )
                )}
                {asking && (
                  <div className="flex flex-col gap-2">
                    <Skeleton className="h-8 w-2/3 self-end" />
                    <Skeleton className="h-20 w-full" />
                  </div>
                )}
              </div>

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
            </>
          )}
        </div>
      </div>
    </div>
  );
}
