"""Retrieval over the ICD-10 reference table.

Two retrievers share one interface:
  * EmbeddingRetriever - cosine similarity over OpenAI embeddings, cached in reference_embeddings
  * KeywordRetriever   - BM25 over tokenized descriptions; no API key needed (tests, offline dev)

Codes written verbatim in the note (e.g. "(M17.11)") are always included at the top.
"""

import hashlib
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.ai.llm import Embedder

_CODE_RE = re.compile(r"\b([A-TV-Z]\d{2}(?:\.\d{1,4})?)\b")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = set(
    "a an and are as at be by for from has have in is it no not of on or the to with without unspecified other "
    "yo m f hx s o a p pt bid daily mg".split()
)


@dataclass
class RetrievedDoc:
    source: str
    ref_id: str
    text: str
    score: float

    def as_dict(self) -> dict:
        return asdict(self)


class Retriever(Protocol):
    name: str

    def retrieve(self, session: Session, query: str, k: int) -> list[RetrievedDoc]: ...


def _icd_docs(session: Session) -> list[tuple[str, str]]:
    return [
        (c.code, f"{c.code} {c.description} ({c.category})")
        for c in session.scalars(select(models.ICD10Code).order_by(models.ICD10Code.code))
    ]


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1]


def _with_explicit_codes(docs: list[tuple[str, str]], query: str, ranked: list[RetrievedDoc], k: int) -> list[RetrievedDoc]:
    by_code = dict(docs)
    explicit = [c for c in dict.fromkeys(_CODE_RE.findall(query)) if c in by_code]
    pinned = [RetrievedDoc("icd10", c, by_code[c], 1.0) for c in explicit]
    rest = [d for d in ranked if d.ref_id not in explicit]
    return (pinned + rest)[: max(k, len(pinned))]


class KeywordRetriever:
    name = "bm25"

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b

    def retrieve(self, session: Session, query: str, k: int) -> list[RetrievedDoc]:
        docs = _icd_docs(session)
        if not docs:
            return []
        doc_tokens = [_tokens(text) for _, text in docs]
        avgdl = sum(map(len, doc_tokens)) / len(doc_tokens)
        df = Counter(t for toks in doc_tokens for t in set(toks))
        n = len(docs)
        q = set(_tokens(query))

        ranked = []
        for (code, text), toks in zip(docs, doc_tokens):
            tf = Counter(toks)
            score = 0.0
            for t in q & tf.keys():
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * tf[t] * (self.k1 + 1) / (tf[t] + self.k1 * (1 - self.b + self.b * len(toks) / avgdl))
            if score > 0:
                ranked.append(RetrievedDoc("icd10", code, text, round(score, 4)))
        ranked.sort(key=lambda d: d.score, reverse=True)
        return _with_explicit_codes(docs, query, ranked, k)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class EmbeddingRetriever:
    name = "embedding"

    def __init__(self, embedder: Embedder):
        self.embedder = embedder

    def index(self, session: Session) -> int:
        """Embed any reference docs that are new or changed. Returns how many were embedded."""
        docs = _icd_docs(session)
        cached = {
            e.ref_id: e
            for e in session.scalars(
                select(models.ReferenceEmbedding).where(
                    models.ReferenceEmbedding.source == "icd10",
                    models.ReferenceEmbedding.model == self.embedder.model,
                )
            )
        }
        stale = [
            (code, text, hashlib.sha256(text.encode()).hexdigest())
            for code, text in docs
            if code not in cached or cached[code].content_sha256 != hashlib.sha256(text.encode()).hexdigest()
        ]
        if not stale:
            return 0
        vectors = self.embedder.embed([text for _, text, _ in stale])
        for (code, _, digest), vec in zip(stale, vectors):
            row = cached.get(code) or models.ReferenceEmbedding(source="icd10", ref_id=code, model=self.embedder.model)
            row.content_sha256, row.vector = digest, vec
            session.add(row)
        session.commit()
        return len(stale)

    def retrieve(self, session: Session, query: str, k: int) -> list[RetrievedDoc]:
        self.index(session)
        docs = _icd_docs(session)
        text_by_code = dict(docs)
        vectors = {
            e.ref_id: e.vector
            for e in session.scalars(
                select(models.ReferenceEmbedding).where(
                    models.ReferenceEmbedding.source == "icd10",
                    models.ReferenceEmbedding.model == self.embedder.model,
                )
            )
            if e.ref_id in text_by_code
        }
        [qvec] = self.embedder.embed([query])
        ranked = sorted(
            (RetrievedDoc("icd10", code, text_by_code[code], round(_cosine(qvec, v), 4)) for code, v in vectors.items()),
            key=lambda d: d.score,
            reverse=True,
        )
        return _with_explicit_codes(docs, query, ranked, k)
