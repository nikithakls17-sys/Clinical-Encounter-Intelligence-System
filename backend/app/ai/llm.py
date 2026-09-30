"""Thin wrappers around the OpenAI API so the pipeline can be tested with fakes."""

from dataclasses import dataclass
from typing import Protocol

from app.config import settings


@dataclass
class Completion:
    model: str
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LLMClient(Protocol):
    model: str

    def complete_json(self, messages: list[dict], schema_name: str, schema: dict) -> Completion: ...


class Embedder(Protocol):
    model: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LLMUnavailable(RuntimeError):
    pass


def _client():
    if not settings.openai_api_key:
        raise LLMUnavailable("OPENAI_API_KEY is not set")
    from openai import OpenAI

    return OpenAI(api_key=settings.openai_api_key, timeout=60)


class OpenAIChat:
    def __init__(self, model: str | None = None):
        self.model = model or settings.openai_model
        self._openai = _client()

    def complete_json(self, messages: list[dict], schema_name: str, schema: dict) -> Completion:
        resp = self._openai.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        )
        usage = resp.usage
        return Completion(
            model=resp.model,
            text=resp.choices[0].message.content or "",
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
        )


class OpenAIEmbedder:
    def __init__(self, model: str | None = None):
        self.model = model or settings.openai_embedding_model
        self._openai = _client()

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self._openai.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]
