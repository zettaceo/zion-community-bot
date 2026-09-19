from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


WORD_REGEX = re.compile(r"[A-Za-zÀ-ÿ0-9_'-]{2,}")


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in folded if not unicodedata.combining(char))


def _tokens(text: str) -> set[str]:
    return {
        _normalize(match.group(0))
        for match in WORD_REGEX.finditer(text or "")
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
        self.reload()

    def reload(self) -> int:
        self.chunks.clear()
        if not self.directory.exists():
            return 0

        for path in sorted(self.directory.glob("*.md")):
            self.chunks.extend(self._parse_file(path))
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
            scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in scored[: max(1, limit)]]

    def render_context(self, query: str, limit: int = 4) -> str:
        chunks = self.search(query, limit)
        if not chunks:
            return ""

        rendered: list[str] = []
        for chunk in chunks:
            rendered.append(
                f"[Fonte: {chunk.source} — {chunk.heading}]\n{chunk.text}"
            )
        return "\n\n".join(rendered)
