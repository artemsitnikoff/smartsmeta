import json
import re
import logging

from openai import AsyncOpenAI

from app.config import OPENAI_API_KEY, GPT_MODEL
from app.models import GptResponse

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=OPENAI_API_KEY)


def _parse_json(text: str) -> dict:
    """3-level JSON parsing: direct → markdown fence → brace search."""
    # Level 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Level 2: extract from markdown code fence
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Level 3: find first { ... } block
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break

    raise ValueError(f"Could not parse JSON from GPT response: {text[:500]}")


async def ask_gpt(
    system_prompt: str,
    user_message: str,
    previous_response_id: str | None = None,
) -> tuple[GptResponse, str]:
    """Send a message to GPT and return parsed response + response_id.

    Returns:
        (GptResponse, response_id) tuple
    """
    kwargs: dict = {
        "model": GPT_MODEL,
        "instructions": system_prompt,
        "input": [{"role": "user", "content": user_message}],
    }

    if previous_response_id:
        kwargs["previous_response_id"] = previous_response_id

    logger.info(
        "GPT REQUEST | model=%s prev_id=%s | user_message=%s",
        GPT_MODEL,
        previous_response_id or "None",
        user_message[:200],
    )

    response = await _client.responses.create(**kwargs)

    raw_text = response.output_text
    logger.info(
        "GPT RESPONSE | id=%s | length=%d | text=%s",
        response.id,
        len(raw_text),
        raw_text[:500],
    )

    data = _parse_json(raw_text)
    parsed = GptResponse.model_validate(data)

    logger.info("GPT PARSED | status=%s questions=%d", parsed.status, len(parsed.questions))

    return parsed, response.id
