"""Text cleaning, tokenisation, heading detection, chunking and query helpers.

The chunker works per page so every chunk keeps a truthful page number. Chunks
never span pages, which keeps citations precise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# ---------------------------------------------------------------------------
# Cleaning and tokenisation
# ---------------------------------------------------------------------------

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTI_BLANK_LINES = re.compile(r"\n{3,}")
_WORD_RE = re.compile(r"[a-z0-9]+")
_TOKEN_RE = re.compile(r"\w+")

# PDF extractors can return typographic ligatures (oﬃce). Expanding them keeps
# search, chunking and embeddings aligned with the plain words users type.
_LIGATURES = str.maketrans(
    {
        "\ufb00": "ff",
        "\ufb01": "fi",
        "\ufb02": "fl",
        "\ufb03": "ffi",
        "\ufb04": "ffl",
        "\ufb05": "st",
        "\ufb06": "st",
        "\u00a0": " ",
    }
)


def clean_extracted_text(text: str) -> str:
    """Normalise whitespace without rewriting the document's content."""
    text = text.translate(_LIGATURES)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS.sub(" ", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _MULTI_BLANK_LINES.sub("\n\n", text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens used for BM25 and the hashing embedder."""
    return _WORD_RE.findall(text.lower())


def count_tokens(text: str) -> int:
    """Approximate token count (words). Good enough for chunk sizing."""
    return len(_TOKEN_RE.findall(text))


STOPWORDS: set[str] = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "have", "has", "had", "will", "would", "can", "could",
    "should", "may", "might", "must", "shall", "to", "of", "in", "on", "at",
    "for", "with", "about", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "and", "or", "but", "if",
    "then", "than", "that", "this", "these", "those", "there", "here", "it",
    "its", "we", "our", "us", "you", "your", "they", "their", "he", "she",
    "his", "her", "i", "me", "my", "mine", "what", "which", "who", "whom",
    "how", "when", "where", "why", "please", "tell", "give", "show", "any",
    "all", "some", "under", "per", "company", "policy", "policies",
    "many", "much", "get", "gets", "receive", "receives", "entitled",
    "provide", "provides", "offer", "offers", "allow", "allowed",
}


def _stem(token: str) -> str:
    """Very small suffix stripping so 'leaves' matches 'leave'."""
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def content_terms(text: str) -> list[str]:
    """Distinct meaningful terms, in order of appearance."""
    seen: set[str] = set()
    terms: list[str] = []
    for token in tokenize(text):
        if len(token) < 2 or token in STOPWORDS:
            continue
        stemmed = _stem(token)
        if stemmed not in seen:
            seen.add(stemmed)
            terms.append(stemmed)
    return terms


def term_coverage(question: str, evidence_text: str) -> float:
    """Fraction of the question's meaningful terms that appear in evidence."""
    terms = content_terms(question)
    if not terms:
        return 0.0
    evidence_terms = {_stem(t) for t in tokenize(evidence_text) if t not in STOPWORDS}
    hits = sum(1 for term in terms if term in evidence_terms)
    return hits / len(terms)


_YEAR_RE = re.compile(r"\b(19[89]\d|20\d{2})\b")


def detect_reference_years(text: str) -> list[int]:
    """Years mentioned in a question, e.g. 'policy in 2024' -> [2024]."""
    return sorted({int(match) for match in _YEAR_RE.findall(text)})


def year_to_date(year: int) -> date:
    """Reference date used when resolving a historical policy year."""
    if year == date.today().year:
        return date.today()
    return date(year, 12, 31)


_FOLLOWUP_PREFIXES = (
    "what about", "how about", "and what", "what if", "can you elaborate",
    "tell me more", "explain that", "and the", "what else", "elaborate",
    "why is that", "how does that", "and how", "and what about",
)


def is_followup_question(question: str) -> bool:
    lowered = question.strip().lower()
    return len(lowered.split()) <= 6 or lowered.startswith(_FOLLOWUP_PREFIXES)


def expand_followup_query(question: str, previous_user_question: str | None) -> str:
    """Blend the previous user question into a short follow-up query.

    Retrieval is still executed fresh; this only improves the query text.
    """
    if not previous_user_question or not is_followup_question(question):
        return question
    return f"{previous_user_question} {question}"


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_BLANK_LINE_SPLIT = re.compile(r"\n\s*\n")

_HEADING_PATTERNS = (
    re.compile(r"^#{1,6}\s+(.+)$"),
    re.compile(r"^(section|clause|article|appendix|schedule)\s+[\dIVXivx]+(\.\d+)*\s*[:.\-–—]?\s*(.*)$", re.I),
    re.compile(r"^\d+(\.\d+)*[.)]?\s+[A-Z][A-Za-z0-9 &,'\-/]{2,90}$"),
)


def detect_heading(block: str) -> str | None:
    """Return a heading string when a short block looks like a section title."""
    text = block.strip()
    if not text or len(text) > 120 or len(text.split()) > 14:
        return None
    for pattern in _HEADING_PATTERNS:
        match = pattern.match(text)
        if match:
            heading = match.group(match.lastindex) if match.lastindex else match.group(0)
            heading = (heading or text).strip(" #:.-–—")
            return heading[:180] or None
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) >= 4 and sum(ch.isupper() for ch in letters) / len(letters) > 0.85:
        if not text.endswith((".", "!", "?")):
            return text[:180]
    return None


@dataclass
class TextChunk:
    chunk_index: int
    text: str
    page_number: int | None
    section: str | None
    token_count: int


@dataclass
class _Unit:
    text: str
    tokens: int
    section: str | None


class TextChunker:
    """Configurable, page-aware, heading-aware chunker with token overlap."""

    def __init__(self, chunk_size_tokens: int = 650, overlap_tokens: int = 90) -> None:
        if chunk_size_tokens < 50:
            raise ValueError("chunk_size_tokens must be at least 50")
        if overlap_tokens >= chunk_size_tokens:
            raise ValueError("overlap_tokens must be smaller than chunk_size_tokens")
        self.chunk_size = chunk_size_tokens
        self.overlap = overlap_tokens

    def chunk_pages(self, pages: list[tuple[int, str]]) -> list[TextChunk]:
        chunks: list[TextChunk] = []
        for page_number, page_text in pages:
            self._chunk_single_page(page_number, page_text, chunks)
        # Re-number chunks across the whole document.
        for index, chunk in enumerate(chunks):
            chunk.chunk_index = index
        return [chunk for chunk in chunks if chunk.text.strip()]

    # -- internals ---------------------------------------------------------
    def _units_for_page(self, page_text: str, current_section: str | None) -> list[_Unit]:
        units: list[_Unit] = []
        section = current_section
        for block in _BLANK_LINE_SPLIT.split(page_text):
            block = block.strip()
            if not block:
                continue
            heading = detect_heading(block)
            if heading:
                section = heading
            for piece in self._split_oversized_block(block):
                tokens = count_tokens(piece)
                if tokens == 0:
                    continue
                units.append(_Unit(text=piece, tokens=tokens, section=section))
        return units

    def _split_oversized_block(self, block: str) -> list[str]:
        if count_tokens(block) <= self.chunk_size:
            return [block]
        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(block) if s.strip()]
        pieces: list[str] = []
        buffer: list[str] = []
        buffer_tokens = 0
        for sentence in sentences:
            sentence_tokens = count_tokens(sentence)
            if sentence_tokens > self.chunk_size:
                if buffer:
                    pieces.append(" ".join(buffer))
                    buffer, buffer_tokens = [], 0
                pieces.extend(self._split_words(sentence))
                continue
            if buffer_tokens + sentence_tokens > self.chunk_size and buffer:
                pieces.append(" ".join(buffer))
                buffer, buffer_tokens = [], 0
            buffer.append(sentence)
            buffer_tokens += sentence_tokens
        if buffer:
            pieces.append(" ".join(buffer))
        return pieces or [block]

    def _split_words(self, text: str) -> list[str]:
        words = text.split()
        return [" ".join(words[i : i + self.chunk_size]) for i in range(0, len(words), self.chunk_size)]

    def _chunk_single_page(self, page_number: int, page_text: str, out: list[TextChunk]) -> None:
        units = self._units_for_page(page_text, None)
        if not units:
            return

        current: list[_Unit] = []
        current_tokens = 0

        def flush() -> None:
            nonlocal current, current_tokens
            if not current:
                return
            text = "\n\n".join(unit.text for unit in current).strip()
            out.append(
                TextChunk(
                    chunk_index=len(out),
                    text=text,
                    page_number=page_number,
                    section=current[0].section,
                    token_count=current_tokens,
                )
            )

        for unit in units:
            section_changed = bool(current) and unit.section != current[-1].section
            if section_changed and current_tokens >= self.chunk_size // 4:
                # Start a new chunk at section boundaries once the current one
                # carries enough context; section metadata stays citation-accurate.
                flush()
                current, current_tokens = [], 0
            elif current and current_tokens + unit.tokens > self.chunk_size:
                previous_section = current[-1].section
                flush()
                overlap_units: list[_Unit] = []
                overlap_tokens = 0
                # Carry the tail of the previous chunk into the next one, but
                # never across a section boundary.
                if previous_section == unit.section:
                    for previous in reversed(current):
                        if overlap_tokens + previous.tokens > self.overlap:
                            break
                        overlap_units.insert(0, previous)
                        overlap_tokens += previous.tokens
                if overlap_tokens + unit.tokens > self.chunk_size:
                    overlap_units, overlap_tokens = [], 0
                current = overlap_units
                current_tokens = overlap_tokens
            current.append(unit)
            current_tokens += unit.tokens

        flush()
