from __future__ import annotations

import logging
import json
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from zion.agents import AgentId


logger = logging.getLogger("zion.knowledge")

MAX_KNOWLEDGE_FILE_BYTES = 256 * 1024
MIN_RETRIEVAL_SCORE = 0.25
KNOWLEDGE_MANIFEST = "MANIFEST.md"
MANIFEST_JSON_RE = re.compile(
    r"```json\s*(.*?)\s*```",
    re.IGNORECASE | re.DOTALL,
)


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


# Curated product vocabulary keeps short, natural questions useful without
# relying on model memory.  Groups are intentionally small and auditable: if a
# member says "plano profissional", retrieval must reach the same approved
# facts as "plano Pro", while unrelated words are left untouched.
TOKEN_ALIASES = (
    frozenset({"plano", "planos", "tier", "tiers", "nivel", "niveis"}),
    frozenset({
        "beneficio", "beneficios", "vantagem", "vantagens", "recurso",
        "recursos", "inclui", "incluso",
    }),
    frozenset({"free", "gratis", "gratuito", "thrall"}),
    frozenset({"pro", "profissional", "drengr", "freyr"}),
    frozenset({"trader", "berserkr", "thor"}),
    frozenset({"pilot", "piloto", "einherjar", "odin"}),
    frozenset({"assinatura", "mensal", "recorrente", "hird"}),
    frozenset({"passe", "pass", "nft", "panteao"}),
    frozenset({"taxa", "taxas", "fee", "fees"}),
    frozenset({"analise", "analises", "cota", "cotas", "limite", "limites"}),
    frozenset({"preco", "precos", "valor", "valores", "custo", "custos"}),
    frozenset({"comparar", "comparacao", "diferenca", "diferencas"}),
    frozenset({"rede", "redes", "network", "networks", "chain", "chains",
               "blockchain", "blockchains"}),
    frozenset({"ordem", "ordens", "order", "orders"}),
    frozenset({"cex", "corretora", "corretoras", "exchange", "exchanges"}),
)

TIER_ALIASES = {
    "free": frozenset({"free", "gratis", "gratuito", "thrall"}),
    "pro": frozenset({"pro", "profissional", "drengr", "freyr"}),
    "trader": frozenset({"trader", "berserkr", "thor"}),
    "pilot": frozenset({"pilot", "piloto", "einherjar", "odin"}),
}

TOPIC_ALIASES = (
    frozenset({
        "rede", "redes", "network", "networks", "chain", "chains",
        "blockchain", "blockchains",
    }),
    frozenset({
        "cex", "corretora", "corretoras", "exchange", "exchanges",
    }),
    frozenset({
        "terminal", "indicador", "indicadores", "ema", "rsi", "macd",
        "vwap", "bollinger", "stochastic", "obv", "timeframe",
    }),
    frozenset({
        "ordem", "ordens", "market", "limit", "stop", "oco",
    }),
    frozenset({
        "launchpad", "governance", "buy", "on-ramp", "otc", "p2p",
        "nft", "soon", "pre-launch", "coming",
    }),
    frozenset({
        "taxa", "taxas", "fee", "fees", "evm", "solana",
    }),
    frozenset({
        "plano", "planos", "tier", "tiers", "free", "pro", "trader",
        "pilot",
    }),
)


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in folded if not unicodedata.combining(char))


def _agent_id_or_none(agent_id: AgentId | str) -> AgentId | None:
    try:
        return (
            agent_id
            if isinstance(agent_id, AgentId)
            else AgentId(str(agent_id).strip().lower())
        )
    except ValueError:
        return None


def _base_tokens(text: str) -> set[str]:
    tokens = {
        _normalize(match.group(0))
        for match in WORD_REGEX.finditer(text or "")
    }
    return {
        token
        for token in tokens
        if token not in STOPWORDS
    }


def _tokens(text: str) -> set[str]:
    tokens = _base_tokens(text)
    expanded = set(tokens)
    for group in TOKEN_ALIASES:
        if tokens & group:
            expanded.update(group)
    return expanded


def _canonical_heading_bonus(
    query_tokens: set[str],
    heading: str,
) -> float:
    normalized_heading = _normalize(heading)
    if (
        query_tokens & {"ordem", "ordens", "order", "orders"}
        and normalized_heading == "painel de ordens"
    ):
        return 3.0
    if (
        query_tokens
        & {
            "rede", "redes", "network", "networks", "chain", "chains",
            "blockchain", "blockchains",
        }
        and (
            normalized_heading == "redes"
            or normalized_heading.startswith("redes disponiveis")
        )
    ):
        return 2.5
    if (
        query_tokens
        & {"cex", "corretora", "corretoras", "exchange", "exchanges"}
        and normalized_heading in {
            "cex",
            "corretoras cex suportadas",
        }
    ):
        return 2.5
    return 0.0


def _first_bullet_block(text: str) -> list[str]:
    items: list[str] = []
    started = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("- "):
            started = True
            item = line[2:].strip().rstrip(".")
            if item:
                items.append(item)
            continue
        if started and line:
            break
    return items


def _join_pt(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} e {items[1]}"
    return ", ".join(items[:-1]) + f" e {items[-1]}"


def _mentioned_tiers(text: str) -> set[str]:
    tokens = _base_tokens(text)
    return {
        tier
        for tier, aliases in TIER_ALIASES.items()
        if tokens & aliases
    }


def _mentioned_topics(text: str) -> set[int]:
    tokens = _base_tokens(text)
    return {
        index
        for index, aliases in enumerate(TOPIC_ALIASES)
        if tokens & aliases
    }


class KnowledgeClassification(str, Enum):
    PUBLIC = "PUBLIC"
    CONTROLLED = "CONTROLLED"
    INTERNAL = "INTERNAL"
    SECRET = "SECRET"


class KnowledgeSourceStatus(str, Enum):
    CURRENT = "CURRENT"
    HISTORICAL = "HISTORICAL"
    SUPERSEDED = "SUPERSEDED"
    EXCLUDED = "EXCLUDED"


@dataclass(frozen=True, slots=True)
class KnowledgeSource:
    filename: str
    classification: KnowledgeClassification
    status: KnowledgeSourceStatus
    version: str
    source_identity: str
    allowed_agents: frozenset[AgentId]

    def allows(self, agent_id: AgentId) -> bool:
        return (
            self.status is KnowledgeSourceStatus.CURRENT
            and self.classification
            in {
                KnowledgeClassification.PUBLIC,
                KnowledgeClassification.CONTROLLED,
            }
            and agent_id in self.allowed_agents
        )


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    source: str
    heading: str
    text: str
    authority: KnowledgeSource


class KnowledgeBase:
    def __init__(self, directory: Path):
        self.directory = directory
        self.chunks: list[KnowledgeChunk] = []
        self.load_errors: list[str] = []
        self.sources: dict[str, KnowledgeSource] = {}
        self.reload()

    def reload(self) -> int:
        self.chunks.clear()
        self.load_errors.clear()
        self.sources.clear()
        if not self.directory.exists():
            return 0

        root = self.directory.resolve()

        try:
            self.sources = self._load_manifest(root)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            self.load_errors.append(
                f"{KNOWLEDGE_MANIFEST}:{type(exc).__name__}"
            )
            logger.warning(
                "Knowledge manifest rejected | error=%s",
                type(exc).__name__,
            )
            return 0

        for path in sorted(self.directory.glob("*.md")):
            if path.name.lower() in {"readme.md", KNOWLEDGE_MANIFEST.lower()}:
                continue
            try:
                if path.is_symlink():
                    raise ValueError("symlink_not_allowed")

                resolved = path.resolve()
                resolved.relative_to(root)

                if path.stat().st_size > MAX_KNOWLEDGE_FILE_BYTES:
                    raise ValueError("file_too_large")

                authority = self.sources.get(path.name)
                if authority is None:
                    raise ValueError("unclassified_source")
                self.chunks.extend(self._parse_file(path, authority))
            except (OSError, UnicodeError, ValueError) as exc:
                error = f"{path.name}:{type(exc).__name__}"
                self.load_errors.append(error)
                logger.warning(
                    "Knowledge file rejected | file=%s | error=%s",
                    path.name,
                    type(exc).__name__,
                )

        return len(self.chunks)

    def _load_manifest(self, root: Path) -> dict[str, KnowledgeSource]:
        path = root / KNOWLEDGE_MANIFEST
        if path.is_symlink() or not path.is_file():
            raise ValueError("manifest_missing_or_unsafe")
        if path.stat().st_size > MAX_KNOWLEDGE_FILE_BYTES:
            raise ValueError("manifest_too_large")
        text = path.read_text(encoding="utf-8")
        match = MANIFEST_JSON_RE.search(text)
        if match is None:
            raise ValueError("manifest_json_missing")
        payload = json.loads(match.group(1))
        if payload.get("schema_version") != 1:
            raise ValueError("manifest_schema_unsupported")
        rows = payload.get("sources")
        if not isinstance(rows, list):
            raise ValueError("manifest_sources_invalid")

        sources: dict[str, KnowledgeSource] = {}
        for raw in rows:
            if not isinstance(raw, dict):
                raise ValueError("manifest_source_invalid")
            filename = str(raw.get("file", "")).strip()
            if (
                not filename
                or Path(filename).name != filename
                or not filename.lower().endswith(".md")
                or filename.lower() in {
                    "readme.md",
                    KNOWLEDGE_MANIFEST.lower(),
                }
                or filename in sources
            ):
                raise ValueError("manifest_filename_invalid")
            version = str(raw.get("version", "")).strip()
            source_identity = str(raw.get("source_identity", "")).strip()
            raw_agents = raw.get("allowed_agents")
            if not version or not source_identity or not isinstance(
                raw_agents, list
            ):
                raise ValueError("manifest_metadata_incomplete")
            try:
                classification = KnowledgeClassification(
                    str(raw.get("classification", "")).upper()
                )
                status = KnowledgeSourceStatus(
                    str(raw.get("status", "")).upper()
                )
                agents = frozenset(
                    AgentId(str(agent).strip().lower())
                    for agent in raw_agents
                )
            except ValueError as exc:
                raise ValueError("manifest_enum_invalid") from exc
            if not agents:
                raise ValueError("manifest_agents_empty")
            sources[filename] = KnowledgeSource(
                filename=filename,
                classification=classification,
                status=status,
                version=version,
                source_identity=source_identity,
                allowed_agents=agents,
            )
        return sources

    def _parse_file(
        self,
        path: Path,
        authority: KnowledgeSource,
    ) -> list[KnowledgeChunk]:
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
                        authority=authority,
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

    def search(
        self,
        query: str,
        limit: int = 4,
        *,
        agent_id: AgentId | str = AgentId.ZION,
    ) -> list[KnowledgeChunk]:
        selected_agent = _agent_id_or_none(agent_id)
        if selected_agent is None:
            return []
        query_tokens = _tokens(query)
        if not query_tokens:
            return []

        requested_tiers = _mentioned_tiers(query)
        requested_topics = _mentioned_topics(query)

        scored: list[tuple[float, KnowledgeChunk]] = []
        for chunk in self.chunks:
            if not chunk.authority.allows(selected_agent):
                continue
            heading_tiers = _mentioned_tiers(chunk.heading)
            heading_topics = _mentioned_topics(chunk.heading)
            if (
                requested_tiers
                and heading_tiers
                and not requested_tiers.intersection(heading_tiers)
            ):
                # An exact tier question must not be grounded primarily by a
                # different tier merely because both headings contain "plano".
                continue

            chunk_tokens = _tokens(chunk.heading + "\n" + chunk.text)
            overlap = query_tokens & chunk_tokens
            if not overlap:
                continue

            score = len(overlap) / max(1, len(query_tokens))
            heading_overlap = query_tokens & _tokens(chunk.heading)
            score += 0.35 * len(heading_overlap)
            score += _canonical_heading_bonus(
                query_tokens,
                chunk.heading,
            )
            if (
                requested_tiers
                and heading_tiers.intersection(requested_tiers)
                and _normalize(chunk.heading).startswith("plano ")
            ):
                score += 0.75

            topic_overlap = requested_topics & heading_topics
            if topic_overlap:
                # Curated headings are a stronger signal than incidental body
                # mentions. This prevents broad product chunks from outranking
                # the canonical section for requests such as "quais redes?".
                score += 1.5 * len(topic_overlap)

            # Reject a weak incidental overlap in long questions. A heading
            # match may still qualify because headings are curated signals.
            if score < MIN_RETRIEVAL_SCORE:
                continue

            scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in scored[: max(1, limit)]]

    def canonical_finite_answer(
        self,
        query: str,
        *,
        agent_id: AgentId | str = AgentId.ZION,
    ) -> str | None:
        folded = _normalize(query)
        asks_list = bool(
            re.search(
                r"\b(?:quais|liste|lista|tipos|existem|suporta|suportadas|"
                r"suportados|disponiveis|disponivel)\b",
                folded,
            )
        )
        if not asks_list:
            return None

        target_heading: str | None = None
        kind = ""
        if re.search(r"\b(?:ordem|ordens|order|orders)\b", folded):
            target_heading = "painel de ordens"
            kind = "orders"
        elif re.search(
            r"\b(?:rede|redes|network|networks|chain|chains|"
            r"blockchain|blockchains)\b",
            folded,
        ):
            target_heading = "redes"
            kind = "networks"
        elif re.search(
            r"\b(?:cex|corretora|corretoras|exchange|exchanges)\b",
            folded,
        ):
            target_heading = "cex"
            kind = "cex"

        if target_heading is None:
            return None

        selected_agent = _agent_id_or_none(agent_id)
        if selected_agent is None:
            return None

        candidates = [
            chunk
            for chunk in self.chunks
            if _normalize(chunk.heading) == target_heading
            and chunk.authority.allows(selected_agent)
        ]
        if not candidates and kind == "networks":
            candidates = [
                chunk
                for chunk in self.chunks
                if _normalize(chunk.heading).startswith(
                    "redes disponiveis"
                )
                and chunk.authority.allows(selected_agent)
            ]
        if not candidates:
            return None

        items = _first_bullet_block(candidates[0].text)
        if not items:
            return None

        joined = _join_pt(items)
        if kind == "orders":
            return (
                "No Terminal Pro, os tipos de ordem documentados são: "
                f"{joined}."
            )
        if kind == "cex":
            return (
                "As corretoras CEX suportadas no registro público atual são: "
                f"{joined}."
            )

        status = ""
        if any(
            "zetta chain" in _normalize(chunk.text)
            and "coming soon" in _normalize(chunk.text)
            for chunk in candidates
        ):
            status = (
                " A ZETTA Chain está coming soon e ainda não é uma rede ativa."
            )
        return f"As redes ativas são: {joined}.{status}"

    def source_labels(
        self,
        query: str,
        limit: int = 4,
        *,
        agent_id: AgentId | str = AgentId.ZION,
    ) -> list[str]:
        labels: list[str] = []
        for chunk in self.search(query, limit, agent_id=agent_id):
            label = f"{chunk.source} — {chunk.heading}"
            if label not in labels:
                labels.append(label)
        return labels

    def render_context(
        self,
        query: str,
        limit: int = 4,
        max_chars: int = 8000,
        *,
        agent_id: AgentId | str = AgentId.ZION,
    ) -> str:
        chunks = self.search(query, limit, agent_id=agent_id)
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
