"""Evidence validation and answer status classification.

The classification is deliberately conservative: if the retrieved evidence does
not contain the question's key terms, the assistant abstains instead of letting
the LLM answer from general knowledge.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.models.enums import AnswerStatus
from app.services.retrieval_service import RetrievedChunk
from app.utils.text import content_terms, term_coverage

# Words that describe who a policy applies to, not what it is about.
GENERIC_SUBJECTS = {
    "employe",
    "staff",
    "member",
    "worker",
    "person",
    "people",
    "organisation",
    "user",
}


@dataclass
class EvidenceAssessment:
    status: AnswerStatus
    confidence: int
    coverage: float
    best_similarity: float
    reason: str


class ValidationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def assess(self, question: str, chunks: list[RetrievedChunk]) -> EvidenceAssessment:
        if not chunks:
            return EvidenceAssessment(
                status=AnswerStatus.NOT_COVERED,
                confidence=0,
                coverage=0.0,
                best_similarity=0.0,
                reason="No indexed documents matched this question.",
            )

        similarities = [chunk.vector_score or 0.0 for chunk in chunks]
        best_similarity = max(similarities)

        # Judge coverage on the strongest single chunk: merging unrelated chunks
        # can make an off-topic question look partly covered.
        coverage = max(term_coverage(question, chunk.record.text) for chunk in chunks)

        # A question whose subject never appears in the evidence is off-topic,
        # even if incidental words (a city, a pronoun, a date) do match.
        evidence_terms = {
            term for chunk in chunks for term in content_terms(chunk.record.text)
        }
        subject = next(
            (term for term in content_terms(question) if term not in GENERIC_SUBJECTS),
            None,
        )
        subject_missing = subject is not None and subject not in evidence_terms

        if (
            subject_missing
            or best_similarity < self.settings.min_vector_similarity
            or coverage < 0.15
        ):
            return EvidenceAssessment(
                status=AnswerStatus.NOT_COVERED,
                confidence=0,
                coverage=round(coverage, 3),
                best_similarity=round(best_similarity, 3),
                reason=(
                    "The uploaded documents do not contain enough relevant evidence "
                    "to answer this question."
                ),
            )

        similarity_component = min(1.0, best_similarity / 0.6)
        confidence = int(round(100 * (0.55 * coverage + 0.45 * similarity_component)))
        confidence = max(1, min(99, confidence))

        if coverage < 0.55 or best_similarity < self.settings.min_answer_similarity:
            return EvidenceAssessment(
                status=AnswerStatus.PARTIALLY_ANSWERED,
                confidence=min(confidence, 72),
                coverage=round(coverage, 3),
                best_similarity=round(best_similarity, 3),
                reason=(
                    "The documents address part of the question, but not every requested "
                    "detail is covered."
                ),
            )

        return EvidenceAssessment(
            status=AnswerStatus.ANSWERED,
            confidence=confidence,
            coverage=round(coverage, 3),
            best_similarity=round(best_similarity, 3),
            reason="Retrieved evidence directly supports the answer.",
        )
