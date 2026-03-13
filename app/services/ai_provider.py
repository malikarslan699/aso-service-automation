import json
from typing import Any

import httpx

ANTHROPIC_MODEL = "claude-sonnet-4-6"
OPENAI_FALLBACK_MODEL = "gpt-4.1"

PRICING_USD_PER_MILLION: dict[tuple[str, str], dict[str, float]] = {
    ("anthropic", ANTHROPIC_MODEL): {"input": 3.0, "output": 15.0},
    ("openai", OPENAI_FALLBACK_MODEL): {"input": 2.0, "output": 8.0},
}


def estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    rates = PRICING_USD_PER_MILLION.get((provider, model))
    if not rates:
        return 0.0
    input_cost = (max(input_tokens, 0) / 1_000_000) * rates["input"]
    output_cost = (max(output_tokens, 0) / 1_000_000) * rates["output"]
    return round(input_cost + output_cost, 6)


def classify_provider_error(provider: str, message: str, status_code: int | None = None) -> str:
    text = (message or "").lower()
    if status_code in {401, 403} or "invalid x-api-key" in text or "incorrect api key" in text:
        return "auth_invalid"
    if "credit balance is too low" in text or "purchase credits" in text or "billing" in text or status_code == 402:
        return "billing_blocked"
    if status_code == 429 or "rate limit" in text or "too many requests" in text:
        return "rate_limited"
    if "model" in text and ("access" in text or "not found" in text or "unsupported" in text):
        return "model_access_blocked"
    return "provider_error"


def error_class_to_status(error_class: str) -> str:
    if error_class == "billing_blocked":
        return "billing_blocked"
    if error_class == "model_access_blocked":
        return "model_access_blocked"
    if error_class == "auth_invalid":
        return "provider_error"
    if error_class == "rate_limited":
        return "provider_error"
    return "provider_error"


def mask_key_suffix(api_key: str) -> str | None:
    key = (api_key or "").strip()
    if not key:
        return None
    return f"...{key[-4:]}"


def extract_json_object(text: str) -> Any:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Empty model response")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
        raise


def extract_json_array(text: str) -> Any:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Empty model response")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("[")
        end = raw.rfind("]")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
        raise


def anthropic_complete(prompt: str, max_tokens: int, api_key: str, model: str = ANTHROPIC_MODEL) -> dict[str, Any]:
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in message.content if getattr(block, "type", "") == "text").strip()
        input_tokens = int(getattr(message.usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(message.usage, "output_tokens", 0) or 0)
        return {
            "ok": True,
            "provider": "anthropic",
            "model": model,
            "text": text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost": estimate_cost("anthropic", model, input_tokens, output_tokens),
            "status": "inference_healthy",
            "error_class": None,
            "error_message": None,
        }
    except Exception as exc:
        message = str(exc)
        error_class = classify_provider_error("anthropic", message)
        return {
            "ok": False,
            "provider": "anthropic",
            "model": model,
            "text": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost": 0.0,
            "status": error_class_to_status(error_class),
            "error_class": error_class,
            "error_message": message,
        }


def openai_complete(prompt: str, max_tokens: int, api_key: str, model: str = OPENAI_FALLBACK_MODEL) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    try:
        with httpx.Client(timeout=45) as client:
            response = client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        data = response.json()
        if response.status_code >= 300:
            message = data.get("error", {}).get("message") or f"HTTP {response.status_code}"
            error_class = classify_provider_error("openai", message, response.status_code)
            return {
                "ok": False,
                "provider": "openai",
                "model": model,
                "text": "",
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost": 0.0,
                "status": error_class_to_status(error_class),
                "error_class": error_class,
                "error_message": message,
            }
        choice = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        usage = data.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens", 0) or 0)
        output_tokens = int(usage.get("completion_tokens", 0) or 0)
        return {
            "ok": True,
            "provider": "openai",
            "model": model,
            "text": choice.strip(),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost": estimate_cost("openai", model, input_tokens, output_tokens),
            "status": "inference_healthy",
            "error_class": None,
            "error_message": None,
        }
    except Exception as exc:
        message = str(exc)
        error_class = classify_provider_error("openai", message)
        return {
            "ok": False,
            "provider": "openai",
            "model": model,
            "text": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost": 0.0,
            "status": error_class_to_status(error_class),
            "error_class": error_class,
            "error_message": message,
        }


async def check_anthropic_inference(api_key: str) -> dict[str, Any]:
    if not api_key:
        return {
            "connected": False,
            "status": "provider_error",
            "provider_error_class": "auth_invalid",
            "message": "anthropic_api_key not configured",
            "provider": "anthropic",
            "endpoint": "api.anthropic.com",
            "provider_name": "Anthropic",
            "model": ANTHROPIC_MODEL,
            "key_suffix": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost": 0.0,
        }

    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 5,
        "messages": [{"role": "user", "content": "Reply with OK in JSON: {\"ok\": true}"}],
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
            )
        data = response.json()
        if response.status_code >= 300:
            message = data.get("error", {}).get("message") or f"HTTP {response.status_code}"
            error_class = classify_provider_error("anthropic", message, response.status_code)
            return {
                "connected": False,
                "status": error_class_to_status(error_class),
                "provider_error_class": error_class,
                "message": message,
                "provider": "anthropic",
                "endpoint": "api.anthropic.com",
                "provider_name": "Anthropic",
                "model": ANTHROPIC_MODEL,
                "key_suffix": mask_key_suffix(api_key),
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost": 0.0,
            }
        usage = data.get("usage") or {}
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        return {
            "connected": True,
            "status": "inference_healthy",
            "provider_error_class": None,
            "message": "Inference healthy",
            "provider": "anthropic",
            "endpoint": "api.anthropic.com",
            "provider_name": "Anthropic",
            "model": ANTHROPIC_MODEL,
            "key_suffix": mask_key_suffix(api_key),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost": estimate_cost("anthropic", ANTHROPIC_MODEL, input_tokens, output_tokens),
        }
    except Exception as exc:
        message = str(exc)
        error_class = classify_provider_error("anthropic", message)
        return {
            "connected": False,
            "status": error_class_to_status(error_class),
            "provider_error_class": error_class,
            "message": message,
            "provider": "anthropic",
            "endpoint": "api.anthropic.com",
            "provider_name": "Anthropic",
            "model": ANTHROPIC_MODEL,
            "key_suffix": mask_key_suffix(api_key),
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost": 0.0,
        }


async def check_openai_inference(api_key: str) -> dict[str, Any]:
    if not api_key:
        return {
            "connected": False,
            "status": "provider_error",
            "provider_error_class": "auth_invalid",
            "message": "openai_api_key not configured",
            "provider": "openai",
            "endpoint": "api.openai.com",
            "provider_name": "OpenAI",
            "model": OPENAI_FALLBACK_MODEL,
            "key_suffix": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost": 0.0,
        }

    payload = {
        "model": OPENAI_FALLBACK_MODEL,
        "messages": [{"role": "user", "content": "Reply with JSON only: {\"ok\": true}"}],
        "max_tokens": 5,
        "temperature": 0,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        data = response.json()
        if response.status_code >= 300:
            message = data.get("error", {}).get("message") or f"HTTP {response.status_code}"
            error_class = classify_provider_error("openai", message, response.status_code)
            return {
                "connected": False,
                "status": error_class_to_status(error_class),
                "provider_error_class": error_class,
                "message": message,
                "provider": "openai",
                "endpoint": "api.openai.com",
                "provider_name": "OpenAI",
                "model": OPENAI_FALLBACK_MODEL,
                "key_suffix": mask_key_suffix(api_key),
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost": 0.0,
            }
        usage = data.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens", 0) or 0)
        output_tokens = int(usage.get("completion_tokens", 0) or 0)
        return {
            "connected": True,
            "status": "inference_healthy",
            "provider_error_class": None,
            "message": "Inference healthy",
            "provider": "openai",
            "endpoint": "api.openai.com",
            "provider_name": "OpenAI",
            "model": OPENAI_FALLBACK_MODEL,
            "key_suffix": mask_key_suffix(api_key),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost": estimate_cost("openai", OPENAI_FALLBACK_MODEL, input_tokens, output_tokens),
        }
    except Exception as exc:
        message = str(exc)
        error_class = classify_provider_error("openai", message)
        return {
            "connected": False,
            "status": error_class_to_status(error_class),
            "provider_error_class": error_class,
            "message": message,
            "provider": "openai",
            "endpoint": "api.openai.com",
            "provider_name": "OpenAI",
            "model": OPENAI_FALLBACK_MODEL,
            "key_suffix": mask_key_suffix(api_key),
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost": 0.0,
        }
