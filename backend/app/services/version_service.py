"""Document version resolution.

Version selection is deterministic (dates + labels), never delegated to the LLM.
If the currently effective version of a document cannot be chosen safely, the
service asks the user for clarification instead of guessing.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.enums import VersionStatus
from app.utils.text import detect_reference_years, year_to_date


@dataclass
class VersionSelection:
    allowed_version_ids: set[str] = field(default_factory=set)
    versions: list[DocumentVersion] = field(default_factory=list)
    requires_clarification: bool = False
    clarification_message: str | None = None
    notes: list[str] = field(default_factory=list)
    reason: str | None = None


class VersionService:
    def next_version_number(self, session: Session, document_id: str) -> int:
        numbers = session.scalars(
            select(DocumentVersion.version_number).where(DocumentVersion.document_id == document_id)
        ).all()
        return (max(numbers) if numbers else 0) + 1

    def next_label(self, session: Session, document_id: str, preferred: str | None, effective_from: date) -> str:
        existing = set(
            session.scalars(
                select(DocumentVersion.version_label).where(
                    DocumentVersion.document_id == document_id
                )
            ).all()
        )
        if preferred:
            if preferred in existing:
                raise ValueError(f"Version label '{preferred}' already exists for this document.")
            return preferred
        candidate = str(effective_from.year)
        if candidate not in existing:
            return candidate
        number = 2
        while f"{candidate}-v{number}" in existing:
            number += 1
        return f"{candidate}-v{number}"

    def refresh_statuses(self, session: Session, document_id: str) -> None:
        """Mark the newest effective version active and older ones superseded."""
        # Sessions use autoflush=False, so a version added in this transaction
        # must be flushed explicitly before the ranking queries can see it.
        session.flush()
        versions = list(
            session.scalars(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == document_id,
                    DocumentVersion.status != VersionStatus.FAILED,
                )
            ).all()
        )
        if not versions:
            return
        newest = max(versions, key=lambda version: (version.effective_from, version.version_number))
        for version in session.scalars(
            select(DocumentVersion).where(DocumentVersion.document_id == document_id)
        ).all():
            if version.status == VersionStatus.FAILED:
                continue
            version.status = (
                VersionStatus.ACTIVE if version.id == newest.id else VersionStatus.SUPERSEDED
            )

    # -- query-time selection ----------------------------------------------
    def select_versions(
        self,
        session: Session,
        question: str,
        explicit_version_ids: list[str] | None = None,
        document_ids: list[str] | None = None,
    ) -> VersionSelection:
        query = (
            select(DocumentVersion)
            .join(Document)
            .options(selectinload(DocumentVersion.document))
            .where(DocumentVersion.status != VersionStatus.FAILED)
        )
        if document_ids:
            query = query.where(DocumentVersion.document_id.in_(document_ids))
        versions = list(session.scalars(query).all())

        if not versions:
            return VersionSelection(
                reason="No processed document versions are available to search."
            )

        if explicit_version_ids:
            wanted = set(explicit_version_ids)
            selected = [version for version in versions if version.id in wanted]
            missing = wanted - {version.id for version in selected}
            if missing:
                return VersionSelection(
                    reason="Some requested document versions do not exist or are not available."
                )
            return VersionSelection(
                allowed_version_ids=wanted,
                versions=selected,
                notes=["An explicit document version filter was applied."],
            )

        by_document: dict[str, list[DocumentVersion]] = defaultdict(list)
        for version in versions:
            by_document[version.document_id].append(version)

        years = detect_reference_years(question)
        target_year = years[-1] if years else None
        reference_date = year_to_date(target_year) if target_year else date.today()

        selection = VersionSelection()
        ambiguous_documents: list[str] = []
        unavailable_documents: list[str] = []

        for document_versions in by_document.values():
            document = document_versions[0].document
            chosen = self._choose_version(document_versions, reference_date, target_year)

            if chosen == "ambiguous":
                ambiguous_documents.append(document.filename)
                continue
            if chosen is None:
                unavailable_documents.append(document.filename)
                continue

            selection.versions.append(chosen)
            selection.allowed_version_ids.add(chosen.id)

        if target_year:
            if selection.versions:
                if target_year == date.today().year:
                    note = f"Using the document versions effective in {target_year}."
                elif target_year < date.today().year:
                    note = f"Using the document versions effective in {target_year} (historical query)."
                else:
                    note = f"Using the document versions effective in {target_year} (future-dated query)."
                selection.notes.append(note)
            else:
                selection.notes.append(f"No document version covers {target_year}.")
        else:
            selection.notes.append("Using the currently effective document versions.")

        if unavailable_documents:
            scope = f"on {reference_date.isoformat()}" if target_year else "today"
            selection.notes.append(
                "No version is effective "
                + scope
                + " for: "
                + ", ".join(sorted(set(unavailable_documents)))
                + "."
            )

        if ambiguous_documents:
            selection.requires_clarification = True
            selection.clarification_message = self._clarification_message(
                by_document, ambiguous_documents, reference_date
            )

        if not selection.allowed_version_ids and not selection.requires_clarification:
            selection.reason = (
                f"No document version is effective on {reference_date.isoformat()}."
                if target_year
                else "No currently effective document version is available."
            )

        return selection

    def _choose_version(
        self, versions: list[DocumentVersion], reference_date: date, target_year: int | None
    ) -> DocumentVersion | str | None:
        if target_year is not None:
            # A year in the question selects versions whose effective period
            # overlaps that calendar year - never simply the highest version.
            window_start = date(target_year, 1, 1)
            window_end = date(target_year, 12, 31)
            effective = [
                version
                for version in versions
                if version.effective_from <= window_end
                and (version.effective_to is None or version.effective_to >= window_start)
            ]
            if target_year > date.today().year:
                # Do not assume an open-ended version stays in force in a future
                # year that no uploaded document covers.
                effective = [
                    version
                    for version in effective
                    if version.effective_from >= window_start
                    or (version.effective_to is not None and version.effective_to >= window_start)
                ]
            if not effective:
                # Fall back to a label lookup (e.g. a version labelled "2024" that
                # was uploaded later but intentionally represents that year).
                effective = [
                    version for version in versions if str(target_year) in version.version_label
                ]
        else:
            effective = [
                version
                for version in versions
                if version.effective_from <= reference_date
                and (version.effective_to is None or version.effective_to >= reference_date)
            ]

        if not effective:
            return None

        latest_date = max(version.effective_from for version in effective)
        latest = [version for version in effective if version.effective_from == latest_date]
        if len(latest) > 1:
            active = [version for version in latest if version.status == VersionStatus.ACTIVE]
            if len(active) == 1:
                return active[0]
            return "ambiguous"
        return latest[0]

    def _clarification_message(
        self,
        by_document: dict[str, list[DocumentVersion]],
        ambiguous_documents: list[str],
        reference_date: date,
    ) -> str:
        parts = [
            "I found more than one equally valid document version for "
            f"{reference_date.isoformat()}, so I will not guess which one to use."
        ]
        for document_versions in by_document.values():
            document = document_versions[0].document
            if document.filename not in ambiguous_documents:
                continue
            options = ", ".join(
                f"{version.version_label} (effective {version.effective_from.isoformat()})"
                for version in sorted(
                    document_versions, key=lambda version: version.effective_from, reverse=True
                )
                if version.status != VersionStatus.FAILED
            )
            parts.append(f"{document.filename}: {options}.")
        parts.append("Please specify the version label or the year you need.")
        return " ".join(parts)
