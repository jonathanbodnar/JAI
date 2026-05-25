"""Thin LangChain wrapper that points ChatOpenAI at OpenRouter.

OpenRouter is OpenAI-API compatible, so we can reuse the entire LangChain
ecosystem (tool calling, streaming, structured output) just by overriding
`base_url` and `default_headers`.
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from ..config import Settings, get_settings


def openrouter_chat(
    model: str,
    *,
    temperature: float = 0.3,
    max_tokens: int | None = None,
    streaming: bool = True,
    settings: Settings | None = None,
) -> ChatOpenAI:
    s = settings or get_settings()
    return ChatOpenAI(
        model=model,
        api_key=s.openrouter_api_key,
        base_url="https://openrouter.ai/api/v1",
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=streaming,
        default_headers={
            "HTTP-Referer": s.openrouter_app_url,
            "X-Title": s.openrouter_app_name,
        },
    )


def openrouter_embeddings(
    model: str | None = None,
    *,
    settings: Settings | None = None,
) -> OpenAIEmbeddings:
    s = settings or get_settings()
    return OpenAIEmbeddings(
        model=model or s.jai_model_embed,
        api_key=s.openrouter_api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": s.openrouter_app_url,
            "X-Title": s.openrouter_app_name,
        },
    )
