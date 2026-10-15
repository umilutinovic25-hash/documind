"""Swappable embedding / LLM providers. Local (Ollama) by default, Claude optional."""
from __future__ import annotations

import hashlib
import os
from typing import Iterator, Protocol

import httpx
import numpy as np

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> np.ndarray: ...


class LLM(Protocol):
    def stream(self, prompt: str) -> Iterator[str]: ...


class OllamaEmbedder:
    def __init__(self, model: str = "bge-m3"):
        self.model = model

    def embed(self, texts: list[str]) -> np.ndarray:
        r = httpx.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": self.model, "input": texts},
            timeout=120,
        )
        r.raise_for_status()
        return np.array(r.json()["embeddings"], dtype=np.float32)


class OllamaLLM:
    def __init__(self, model: str = os.getenv("DOCUMIND_LLM", "gemma3:4b")):
        self.model = model

    def stream(self, prompt: str) -> Iterator[str]:
        import json

        with httpx.stream(
            "POST",
            f"{OLLAMA_URL}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": True},
            timeout=None,
        ) as r:
            for line in r.iter_lines():
                if line:
                    yield json.loads(line).get("response", "")


class ClaudeLLM:
    def __init__(self, model: str = "claude-sonnet-5-5"):
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model

    def stream(self, prompt: str) -> Iterator[str]:
        with self.client.messages.stream(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        ) as s:
            yield from s.text_stream


class HashEmbedder:
    """Deterministic bag-of-words embedder for tests: no model, no network."""

    def __init__(self, dim: int = 256):
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for w in t.lower().split():
                h = int(hashlib.md5(w.strip(".,;:!?").encode()).hexdigest(), 16)
                out[i, h % self.dim] += 1.0
        return out


class EchoLLM:
    def stream(self, prompt: str) -> Iterator[str]:
        yield from ("Odgovor ", "na osnovu ", "izvora [1].")


def make_providers() -> tuple[Embedder, LLM]:
    if os.getenv("ANTHROPIC_API_KEY"):
        return OllamaEmbedder(), ClaudeLLM()
    return OllamaEmbedder(), OllamaLLM()
