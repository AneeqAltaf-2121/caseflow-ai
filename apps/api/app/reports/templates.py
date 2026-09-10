"""Section templates per report type: each entry is (heading, question) —
`question` is answered by RagService exactly like a chat message, over the
project's whole document set (no conversation history involved)."""

from dataclasses import dataclass

from app.models.report import ReportType


@dataclass(frozen=True)
class SectionSpec:
    heading: str
    question: str


REPORT_TEMPLATES: dict[ReportType, list[SectionSpec]] = {
    ReportType.EXECUTIVE_SUMMARY: [
        SectionSpec(
            "Overview",
            "Provide a concise executive summary of the key facts, parties, and issues "
            "raised in these documents.",
        ),
    ],
    ReportType.EVIDENCE_REPORT: [
        SectionSpec(
            "Key Evidence",
            "List and summarize the most important pieces of evidence found in these "
            "documents, in order of significance.",
        ),
    ],
    ReportType.RISK_ANALYSIS: [
        SectionSpec(
            "Identified Risks",
            "Identify and analyze potential risks, liabilities, or concerns raised in "
            "these documents.",
        ),
    ],
    ReportType.CHRONOLOGY: [
        SectionSpec(
            "Timeline of Events",
            "Construct a chronological timeline of events described in these documents, "
            "in date order where dates are available.",
        ),
    ],
    ReportType.CONTRADICTION_REPORT: [
        SectionSpec(
            "Contradictions and Inconsistencies",
            "Identify any contradictions, inconsistencies, or conflicting statements "
            "across these documents.",
        ),
    ],
    ReportType.RESEARCH_MEMO: [
        SectionSpec(
            "Summary",
            "Summarize the central question or matter these documents address.",
        ),
        SectionSpec(
            "Analysis",
            "Analyze the relevant facts and evidence in these documents in detail.",
        ),
        SectionSpec(
            "Recommendations",
            "Based on these documents, what recommendations or next steps follow?",
        ),
    ],
}


def sections_for(report_type: ReportType) -> list[SectionSpec]:
    return REPORT_TEMPLATES[report_type]
