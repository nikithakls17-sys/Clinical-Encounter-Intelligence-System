"""FastAPI dependencies for the AI pipeline. Tests override these with fakes."""

from fastapi import HTTPException

from app.ai.llm import LLMClient, LLMUnavailable, OpenAIChat, OpenAIEmbedder
from app.ai.retrieval import EmbeddingRetriever, KeywordRetriever, Retriever
from app.config import settings


def get_llm() -> LLMClient:
    try:
        return OpenAIChat()
    except LLMUnavailable as exc:
        raise HTTPException(503, f"AI extraction unavailable: {exc}") from exc


def get_retriever() -> Retriever:
    if settings.openai_api_key:
        return EmbeddingRetriever(OpenAIEmbedder())
    return KeywordRetriever()
