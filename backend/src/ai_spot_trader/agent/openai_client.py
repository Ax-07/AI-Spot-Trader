from typing import Any, cast

import httpx
from pydantic import SecretStr

from ai_spot_trader.agent.errors import LLMProviderError, LLMTransportError
from ai_spot_trader.domain.enums import LLMModel


class OpenAIResponsesClient:
    """Minimal OpenAI Responses API adapter for strategic and conversational calls."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 30.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.get_secret_value():
            raise ValueError("OpenAI API key cannot be empty")
        if timeout_seconds <= 0:
            raise ValueError("OpenAI timeout must be positive")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._http_client = http_client

    async def generate_structured_decision(
        self,
        *,
        model: LLMModel,
        instructions: str,
        input_text: str,
        schema: dict[str, Any],
    ) -> str:
        request = {
            "model": model.value,
            "instructions": instructions,
            "input": input_text,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "agent_decision_v1",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        response = await self._responses(request)
        return _extract_output_text(response)

    async def generate_text_response(
        self,
        *,
        model: LLMModel,
        instructions: str,
        input_text: str,
    ) -> str:
        """Generate plain text without tools, persistence, or structured trading output."""

        request = {
            "model": model.value,
            "instructions": instructions,
            "input": input_text,
            "store": False,
        }
        response = await self._responses(request)
        return _extract_output_text(response)

    async def _responses(self, request: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        return await self._post(request=request, headers=headers)

    async def _post(
        self,
        *,
        request: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        try:
            if self._http_client is not None:
                response = await self._http_client.post(
                    f"{self._base_url}/responses",
                    json=request,
                    headers=headers,
                    timeout=self._timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(
                        f"{self._base_url}/responses",
                        json=request,
                        headers=headers,
                    )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            raise LLMTransportError(
                f"OpenAI Responses API returned HTTP {status_code}"
            ) from None
        except httpx.HTTPError:
            raise LLMTransportError("OpenAI Responses API request failed") from None

        try:
            data = response.json()
        except ValueError:
            raise LLMProviderError("OpenAI Responses API returned invalid JSON") from None
        if not isinstance(data, dict):
            raise LLMProviderError("OpenAI Responses API returned an invalid response envelope")
        return cast(dict[str, Any], data)


def _extract_output_text(response: dict[str, Any]) -> str:
    if response.get("status") != "completed":
        raise LLMProviderError("OpenAI Responses API response is incomplete")

    output = response.get("output")
    if not isinstance(output, list):
        raise LLMProviderError("OpenAI Responses API response has no output list")

    texts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "refusal":
                raise LLMProviderError("OpenAI Responses API refused the request")
            text = part.get("text")
            if part.get("type") == "output_text" and isinstance(text, str):
                texts.append(text)

    if len(texts) != 1 or not texts[0].strip():
        raise LLMProviderError(
            "OpenAI Responses API must return exactly one non-empty output_text"
        )
    return texts[0]
