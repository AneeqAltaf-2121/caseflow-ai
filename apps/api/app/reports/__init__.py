"""Report generation (Phase 24): workflows beyond chat — an executive
summary, evidence report, risk analysis, chronology, contradiction
report, or research memo, each built from a fixed set of section prompts
(see templates.py) answered through the same citation-grounded RagService
used for chat (Phase 19), so every section keeps its own citations. Runs
as a background job (see app/jobs/reports.py), same pattern as document
ingestion (Phase 8).
"""
