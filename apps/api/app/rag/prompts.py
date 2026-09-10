"""Prompt templates for citation-grounded generation.

A single hardcoded template for now — versioned/tracked PromptVersion
rows (with named variants like "rag_answer_v2") are Phase 22's job. This
is effectively "rag_answer_v1".
"""

SYSTEM_PROMPT = (
    "You are a research assistant answering questions using ONLY the "
    "numbered source passages provided below. Cite every factual claim "
    "with the matching [n] marker(s) immediately after it, e.g. 'The "
    "agreement terminates after 90 days [2].' Never cite a source number "
    "that wasn't provided. If the sources don't contain enough "
    "information to answer the question, say so explicitly rather than "
    "guessing or using outside knowledge."
)


def build_user_prompt(*, question: str, context: str) -> str:
    if not context:
        return f"No source passages were found for this project.\n\nQuestion: {question}"
    return f"Sources:\n{context}\n\nQuestion: {question}"
