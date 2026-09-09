"""Thin client for Foundry Local's OpenAI-compatible API.

This is the ONLY module that knows how to talk to Foundry Local. Everything
else in the service depends on the small surface exposed here (`generate`,
`embed`, `health`) so the inference backend stays swappable.

Notes on Foundry Local (>= 0.10):
  * The daemon binds to a DYNAMIC port -- configure `FOUNDRY_LOCAL_URL`.
  * Models are NOT auto-loaded by the HTTP API. Loading happens through the
    CLI's native interop layer (`foundry model load <alias>`), so when a model
    is missing we raise a dedicated error carrying the exact command to run.
  * Errors come back as a JSON `error` object, sometimes alongside HTTP 200.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def discover_base_url() -> str | None:
    """Ask the Foundry CLI where the daemon is listening.

    The daemon picks a new random port on every restart, so a hard-coded
    FOUNDRY_LOCAL_URL goes stale routinely during local development. Returns
    None when the CLI is unavailable (e.g. inside a container).
    """
    try:
        result = subprocess.run(
            ["foundry", "server", "status", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("Foundry CLI not available for discovery: %s", exc)
        return None

    if result.returncode != 0:
        return None
    try:
        status = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    urls = status.get("webUrls") or []
    if status.get("running") and urls:
        return str(urls[0]).rstrip("/")
    return None


class FoundryError(RuntimeError):
    """Base class for every Foundry Local failure."""

    user_message = (
        "AI service is currently unavailable. Please ensure Foundry Local is running."
    )


class FoundryUnavailableError(FoundryError):
    """The daemon could not be reached at all."""


class FoundryModelNotLoadedError(FoundryError):
    """The daemon is up but the requested model is not resident in memory."""

    def __init__(self, model: str) -> None:
        self.model = model
        super().__init__(
            f"Model {model!r} is not loaded in Foundry Local. "
            f"Run: foundry model load {model}"
        )

    @property
    def user_message(self) -> str:  # type: ignore[override]
        return (
            f"The local model {self.model!r} is not loaded. "
            f"Start it with: foundry model load {self.model}"
        )


class FoundryResponseError(FoundryError):
    """The daemon replied, but not with something usable."""


@dataclass(frozen=True)
class FoundryHealth:
    """Snapshot of the local inference backend, surfaced on /health."""

    reachable: bool
    base_url: str
    chat_model: str
    embedding_model: str
    available_models: tuple[str, ...] = ()
    detail: str | None = None


class FoundryLocalClient:
    """Synchronous client for chat completions and embeddings."""

    def __init__(
        self,
        base_url: str | None = None,
        chat_model: str | None = None,
        embedding_model: str | None = None,
        timeout_seconds: float | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        auto_load: bool | None = None,
    ) -> None:
        self.base_url = (base_url or settings.foundry_local_url).rstrip("/")
        self.chat_model = chat_model or settings.foundry_model
        self.embedding_model = embedding_model or settings.foundry_embedding_model
        self.timeout_seconds = timeout_seconds or settings.foundry_timeout_seconds
        self.max_tokens = max_tokens or settings.foundry_max_tokens
        self.temperature = (
            settings.foundry_temperature if temperature is None else temperature
        )
        self.auto_load = settings.foundry_auto_load if auto_load is None else auto_load
        self._client = httpx.Client(
            base_url=self.base_url, timeout=httpx.Timeout(self.timeout_seconds)
        )
        # Models this process has already nudged into memory.
        self._loaded: set[str] = set()
        self._rediscovered = False

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Run a single-turn completion and return the assistant's text."""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, max_tokens=max_tokens, temperature=temperature)

    def chat(
        self,
        messages: Sequence[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Run a multi-turn completion and return the assistant's text."""
        payload: dict[str, Any] = {
            "model": self.chat_model,
            "messages": list(messages),
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": self.temperature if temperature is None else temperature,
            "stream": False,
        }
        data = self._post("/v1/chat/completions", payload, model=self.chat_model)

        choices = data.get("choices") or []
        if not choices:
            raise FoundryResponseError("Foundry Local returned no choices.")
        message = choices[0].get("message") or choices[0].get("delta") or {}
        content = (message.get("content") or "").strip()
        if not content:
            raise FoundryResponseError("Foundry Local returned an empty completion.")

        usage = data.get("usage") or {}
        logger.debug(
            "foundry.chat model=%s prompt_tokens=%s completion_tokens=%s",
            self.chat_model,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )
        return content

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        """Embed a batch of texts. Result order matches the input order."""
        batch = list(texts)
        if not batch:
            return []

        payload = {"model": self.embedding_model, "input": batch}
        data = self._post("/v1/embeddings", payload, model=self.embedding_model)

        items = data.get("data") or []
        if len(items) != len(batch):
            raise FoundryResponseError(
                f"Embedding count mismatch: sent {len(batch)}, received {len(items)}."
            )
        # The API echoes an `index`; sort defensively before stripping it.
        ordered = sorted(items, key=lambda item: item.get("index", 0))
        return [item["embedding"] for item in ordered]

    def health(self) -> FoundryHealth:
        """Best-effort probe used by /health. Never raises."""
        try:
            try:
                response = self._client.get("/v1/models")
            except httpx.ConnectError:
                if not self._rebase():
                    raise
                response = self._client.get("/v1/models")
            response.raise_for_status()
            models = tuple(
                entry.get("parent") or entry.get("id", "")
                for entry in (response.json().get("data") or [])
            )
            return FoundryHealth(
                reachable=True,
                base_url=self.base_url,
                chat_model=self.chat_model,
                embedding_model=self.embedding_model,
                available_models=models,
            )
        except Exception as exc:  # noqa: BLE001 - health must never propagate
            logger.warning("Foundry Local health probe failed: %s", exc)
            return FoundryHealth(
                reachable=False,
                base_url=self.base_url,
                chat_model=self.chat_model,
                embedding_model=self.embedding_model,
                detail=str(exc),
            )

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _post(self, path: str, payload: dict[str, Any], model: str) -> dict[str, Any]:
        """POST to Foundry, translating transport and API errors into ours."""
        try:
            response = self._client.post(path, json=payload)
        except httpx.ConnectError as exc:
            # The daemon may simply have restarted onto a different port.
            if self._rebase():
                return self._post(path, payload, model)
            raise FoundryUnavailableError(
                f"Cannot reach Foundry Local at {self.base_url}. Is the daemon running?"
            ) from exc
        except httpx.TimeoutException as exc:
            raise FoundryUnavailableError(
                f"Foundry Local timed out after {self.timeout_seconds:.0f}s."
            ) from exc
        except httpx.RequestError as exc:
            # Covers ReadError/RemoteProtocolError: the daemon accepted the
            # request and then died mid-flight, which is what running out of
            # VRAM looks like from this side.
            raise FoundryUnavailableError(
                f"The connection to Foundry Local was lost ({type(exc).__name__}). "
                "The daemon may have run out of memory -- check `foundry server status` "
                "and consider lowering MAX_CONTEXT_CHARS or FOUNDRY_MAX_TOKENS."
            ) from exc

        data = self._parse(response)
        error = data.get("error")
        if not error:
            return data

        message = str(error.get("message", error))
        if "not loaded" in message.lower():
            # One recovery attempt through the CLI, then retry the request once.
            if self.auto_load and model not in self._loaded and self._cli_load(model):
                self._loaded.add(model)
                return self._post(path, payload, model)
            raise FoundryModelNotLoadedError(model)
        raise FoundryResponseError(f"Foundry Local error: {message}")

    def _rebase(self) -> bool:
        """Re-point at the daemon after a restart moved it to a new port.

        Attempted at most once per process so a genuinely dead daemon still
        fails fast instead of shelling out on every request.
        """
        if self._rediscovered or not settings.foundry_auto_discover:
            return False
        self._rediscovered = True

        discovered = discover_base_url()
        if not discovered or discovered == self.base_url:
            return False

        logger.warning(
            "Foundry Local moved from %s to %s; reconnecting.",
            self.base_url, discovered,
        )
        self.base_url = discovered
        self._client.close()
        self._client = httpx.Client(
            base_url=self.base_url, timeout=httpx.Timeout(self.timeout_seconds)
        )
        return True

    @staticmethod
    def _parse(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise FoundryResponseError(
                f"Foundry Local returned non-JSON (HTTP {response.status_code})."
            ) from exc
        if not isinstance(data, dict):
            raise FoundryResponseError("Foundry Local returned an unexpected payload.")
        return data

    @staticmethod
    def _cli_load(model: str) -> bool:
        """Opt-in convenience: ask the local CLI to load a model.

        Only works when the service runs on the same host as Foundry Local
        (i.e. not in a container), hence FOUNDRY_AUTO_LOAD defaults to false.
        """
        logger.info("Attempting to load model %r via the Foundry CLI...", model)
        try:
            result = subprocess.run(
                ["foundry", "model", "load", model],
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("Foundry CLI auto-load unavailable: %s", exc)
            return False
        if result.returncode != 0:
            logger.warning("Foundry CLI auto-load failed: %s", result.stderr.strip())
            return False
        logger.info("Model %r loaded.", model)
        return True


_client: FoundryLocalClient | None = None


def get_foundry_client() -> FoundryLocalClient:
    """Return the process-wide Foundry client (used as a FastAPI dependency)."""
    global _client
    if _client is None:
        _client = FoundryLocalClient()
    return _client
