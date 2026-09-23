from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


logger = logging.getLogger("zion.knowledge")

MAX_KNOWLEDGE_FILE_BYTES = 256 * 1024
MIN_RETRIEVAL_SCORE = 0.25


WORD_REGEX = re.compile(r"[A-Za-zÀ-ÿ0-9_'-]{2,}")

STOPWORDS = {
    "a", "as", "ao", "aos", "com", "como", "da", "das", "de", "do",
    "dos", "e", "em", "esta", "este", "eu", "isso", "isto", "na", "nas",
    "no", "nos", "o", "os", "ou", "para", "por", "que", "qual", "quais",
    "se", "sem", "ser", "sobre", "um", "uma",
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "how", "in", "is", "it", "of", "on", "or", "that", "the", "this",
    "to", "what", "when", "where", "which", "who", "why", "with",
}


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in folded if not unicodedata.combining(char))


def _tokens(text: str) -> set[str]:
    tokens = {
        _normalize(match.group(0))
        for match in WORD_REGEX.finditer(text or "")
    }
    return {
        token
        for token in tokens
        if token not in STOPWORDS
    }


@dataclass(slots=True)
class KnowledgeChunk:
    source: str
    heading: str
    text: str


class KnowledgeBase:
    def __init__(self, directory: Path):
        self.directory = directory
        self.chunks: list[KnowledgeChunk] = []
        self.load_errors: list[str] = []
        self.reload()

    def reload(self) -> int:
        self.chunks.clear()
        self.load_errors.clear()
        if not self.directory.exists():
            return 0

        root = self.directory.resolve()

        for path in sorted(self.directory.glob("*.md")):
            try:
                if path.is_symlink():
                    raise ValueError("symlink_not_allowed")

                resolved = path.resolve()
                resolved.relative_to(root)

                if path.stat().st_size > MAX_KNOWLEDGE_FILE_BYTES:
                    raise ValueError("file_too_large")

                self.chunks.extend(self._parse_file(path))
            except (OSError, UnicodeError, ValueError) as exc:
                error = f"{path.name}:{type(exc).__name__}"
                self.load_errors.append(error)
                logger.warning(
                    "Knowledge file rejected | file=%s | error=%s",
                    path.name,
                    type(exc).__name__,
                )

        return len(self.chunks)

    def _parse_file(self, path: Path) -> list[KnowledgeChunk]:
        text = path.read_text(encoding="utf-8")
        chunks: list[KnowledgeChunk] = []
        heading = path.stem
        buffer: list[str] = []

        def flush() -> None:
            nonlocal buffer
            body = "\n".join(buffer).strip()
            if body:
                chunks.append(
                    KnowledgeChunk(
                        source=path.name,
                        heading=heading,
                        text=body,
                    )
                )
            buffer = []

        for line in text.splitlines():
            if line.startswith("#"):
                flush()
                heading = line.lstrip("#").strip() or path.stem
            else:
                buffer.append(line)
        flush()
        return chunks

    def search(self, query: str, limit: int = 4) -> list[KnowledgeChunk]:
        query_tokens = _tokens(query)
        if not query_tokens:
            return []

        scored: list[tuple[float, KnowledgeChunk]] = []
        for chunk in self.chunks:
            chunk_tokens = _tokens(chunk.heading + "\n" + chunk.text)
            overlap = query_tokens & chunk_tokens
            if not overlap:
                continue

            score = len(overlap) / max(1, len(query_tokens))
            heading_overlap = query_tokens & _tokens(chunk.heading)
            score += 0.35 * len(heading_overlap)

            # Reject a weak incidental overlap in long questions. A heading
            # match may still qualify because headings are curated signals.
            if score < MIN_RETRIEVAL_SCORE:
                continue

            scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in scored[: max(1, limit)]]

    def source_labels(
        self,
        query: str,
        limit: int = 4,
    ) -> list[str]:
        labels: list[str] = []
        for chunk in self.search(query, limit):
            label = f"{chunk.source} — {chunk.heading}"
            if label not in labels:
                labels.append(label)
        return labels

    def render_context(
        self,
        query: str,
        limit: int = 4,
        max_chars: int = 8000,
    ) -> str:
        chunks = self.search(query, limit)
        if not chunks:
            return ""

        remaining = max(256, int(max_chars))
        rendered: list[str] = []

        for chunk in chunks:
            # The model needs approved content, not repository metadata.
            # Keeping file names out of the prompt prevents internal knowledge
            # layout from leaking into community-facing answers.
            prefix = f"[Contexto oficial: {chunk.heading}]\n"
            if len(prefix) >= remaining:
                break

            body_budget = remaining - len(prefix)
            body = chunk.text[:body_budget]
            rendered.append(prefix + body)
            remaining -= len(prefix) + len(body) + 2

            if remaining <= 0:
                break

        return "\n\n".join(rendered)
