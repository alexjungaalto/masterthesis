#!/usr/bin/env python3
"""Shared LLM client for the thesis linters.

Default gateway: the Aalto AI API (Azure OpenAI gateway; Responses API at
AALTO_AZURE_URL, Ocp-Apim-Subscription-Key auth from $AALTO_API_KEY,
GPT-5-family models with dated IDs; Aalto network/VPN only). Alternatives
via base_url: the self-hosted Aalto LLM Gateway (LLMGW_BASE_URL below;
OpenAI-style chat completions, Bearer $AALTO_LLM_KEY, Qwen models such as
Qwen/Qwen3-30B-A3B-Instruct-2507-FP8; models scale to zero and answer 503
while spinning up) and any OpenAI-style endpoint such as OpenRouter
($OPENROUTER_API_KEY). LLMClient picks protocol and key from the URL.

Stdlib urllib only — no SDK needed.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, Optional, Tuple

AALTO_AZURE_URL = "https://aalto-openai-apigw.azure-api.net/v1/openai/responses"
LLMGW_BASE_URL = "https://llm-gateway.k8s.aalto.fi/api/v1"
BASE_URL = os.environ.get("LLM_BASE_URL", AALTO_AZURE_URL)

BASE_URL_HELP = ("LLM endpoint (default: the Aalto AI API, "
                 f"{AALTO_AZURE_URL}). Alternatives: the Aalto LLM Gateway "
                 f"({LLMGW_BASE_URL}) or any OpenAI-style endpoint such as "
                 "https://openrouter.ai/api/v1.")
API_KEY_HELP = ("API key (default: $AALTO_API_KEY for the Aalto AI API, "
                "$AALTO_LLM_KEY for the Aalto LLM gateway, "
                "$OPENROUTER_API_KEY otherwise).")


def is_responses_api(base_url: str) -> bool:
    return ("aalto-openai-apigw" in base_url
            or base_url.rstrip("/").endswith("/responses"))


def is_aalto_endpoint(base_url: str) -> bool:
    """True for Aalto-hosted gateways that keep thesis text within Aalto's
    tenant (the Aalto AI API and the Aalto LLM Gateway). These are the only
    endpoints suitable for unpublished manuscripts; anything else is a
    public third-party service."""
    return "aalto-openai-apigw" in base_url or "llm-gateway.k8s.aalto.fi" in base_url


def default_model(base_url: str = BASE_URL) -> str:
    if os.environ.get("LLM_MODEL"):
        return os.environ["LLM_MODEL"]
    if is_responses_api(base_url):
        return "gpt-5-mini-2025-08-07"
    if "llm-gateway" in base_url:
        return "Qwen/Qwen3-30B-A3B-Instruct-2507-FP8"
    return "google/gemini-2.5-flash"


def default_vision_model(base_url: str = BASE_URL) -> str:
    """Model for requests that attach images. On the Aalto AI API the
    GPT-5 family is multimodal; the Aalto LLM Gateway hosts a separate
    vision model."""
    if os.environ.get("LLM_VISION_MODEL"):
        return os.environ["LLM_VISION_MODEL"]
    if "llm-gateway" in base_url:
        return "Qwen/Qwen3-VL-30B-A3B-Instruct-FP8"
    return default_model(base_url)


def _key_from_shell_profile(*names: str) -> Optional[str]:
    """Fallback when the variable is not in the environment: read the
    `export NAME=value` line from ~/.zshenv / ~/.zshrc (a shell whose
    snapshot predates the export line, cron, IDE runners)."""
    found: Dict[str, str] = {}
    for path in ("~/.zshenv", "~/.zshrc"):
        try:
            text = open(os.path.expanduser(path)).read()
        except OSError:
            continue
        for name in names:
            for m in re.finditer(
                    rf"^\s*export\s+{name}=[\"']?([^\"'\n]+)[\"']?\s*$",
                    text, re.M):
                found[name] = m.group(1)
    for name in names:
        if name in found:
            return found[name]
    return None


def default_api_key(base_url: str = BASE_URL) -> Optional[str]:
    if "llm-gateway" in base_url:              # Aalto LLM Gateway
        return (os.environ.get("AALTO_LLM_KEY")
                or _key_from_shell_profile("AALTO_LLM_KEY"))
    if is_responses_api(base_url):             # Aalto AI API (Azure gateway)
        return (os.environ.get("AALTO_API_KEY")
                or os.environ.get("AALTO_OPENAI_API_KEY")
                or _key_from_shell_profile("AALTO_API_KEY",
                                           "AALTO_OPENAI_API_KEY"))
    return (os.environ.get("OPENROUTER_API_KEY")
            or _key_from_shell_profile("OPENROUTER_API_KEY"))


class LLMClient:
    """One JSON-mode request per complete() call; speaks two protocols,
    chosen from the URL: the OpenAI Responses API (Aalto AI API gateway)
    and OpenAI-style chat completions (Aalto LLM Gateway, OpenRouter)."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key
        self.responses = is_responses_api(base_url)

    def complete(self, model: str, system: str, user: str,
                 timeout: float = 120.0, max_tokens: int = 8000,
                 images: Optional[list] = None) -> Tuple[str, dict]:
        """Returns (raw_text, usage_dict). Raises RuntimeError on failure.
        `images` is an optional list of PNG bytes attached to the user
        message (use a vision-capable model, see default_vision_model)."""
        import base64
        if self.responses:
            content = [{"type": "input_text", "text": user}]
            for png in images or []:
                b64 = base64.standard_b64encode(png).decode("ascii")
                content.append({"type": "input_image",
                                "image_url": f"data:image/png;base64,{b64}"})
            body = {
                "model": model,
                "instructions": system,
                "input": [{"role": "user", "content": content}],
                # headroom: gpt-5-family reasoning tokens count against this
                "max_output_tokens": max_tokens + 8000,
                "text": {"format": {"type": "json_object"}},
            }
            fmt_key = "text"
            url = self.base_url
            headers = {"Ocp-Apim-Subscription-Key": self.api_key,
                       "Content-Type": "application/json"}
        else:
            if images:
                content = [{"type": "text", "text": user}]
                for png in images:
                    b64 = base64.standard_b64encode(png).decode("ascii")
                    content.append(
                        {"type": "image_url",
                         "image_url": {"url":
                                       f"data:image/png;base64,{b64}"}})
            else:
                content = user
            body = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": 0,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": content}],
                "response_format": {"type": "json_object"},
            }
            fmt_key = "response_format"
            url = self.base_url.rstrip("/") + "/chat/completions"
            headers = {"Authorization": f"Bearer {self.api_key}",
                       "Content-Type": "application/json",
                       "X-Title": "msc-thesis-linters"}

        data = None
        for attempt in range(11):
            req = urllib.request.Request(
                url, data=json.dumps(body).encode("utf-8"), headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", errors="replace")[:400]
                if e.code == 401:
                    raise RuntimeError(
                        "The LLM gateway rejected the key (401) — check "
                        "AALTO_API_KEY / AALTO_LLM_KEY / OPENROUTER_API_KEY "
                        "/ --api-key.") from e
                if e.code == 400 and fmt_key in body:
                    # Endpoint rejects the JSON-mode format: drop it and
                    # retry (the system prompt demands bare JSON anyway).
                    body.pop(fmt_key)
                    continue
                if e.code in (503, 429) and attempt < 10:
                    # The Aalto LLM gateway scales models to zero; a cold
                    # model answers 503 while its pod spins up.
                    wait = 45
                    print(f"[llm] {e.code} from gateway ({detail[:80]}) — "
                          f"retrying in {wait}s ({attempt + 1}/10)",
                          file=sys.stderr)
                    time.sleep(wait)
                    continue
                raise RuntimeError(f"LLM gateway error {e.code}: {detail}") from e
        if data is None:
            raise RuntimeError("LLM gateway unreachable after retries.")
        if isinstance(data.get("error"), dict) and data["error"]:
            raise RuntimeError(f"LLM gateway error: {data['error']}")

        if self.responses:
            text = "".join(c.get("text", "")
                           for item in data.get("output", [])
                           if item.get("type") == "message"
                           for c in item.get("content", [])
                           if c.get("type") == "output_text")
            u = data.get("usage", {}) or {}
            usage = {"prompt_tokens": u.get("input_tokens", 0),
                     "completion_tokens": u.get("output_tokens", 0),
                     "total_tokens": u.get("total_tokens", 0)}
        else:
            text = data["choices"][0]["message"]["content"] or ""
            u = data.get("usage", {}) or {}
            usage = {"prompt_tokens": u.get("prompt_tokens", 0),
                     "completion_tokens": u.get("completion_tokens", 0),
                     "total_tokens": u.get("total_tokens", 0)}
        return text, usage


def make_client(base_url: str = BASE_URL,
                api_key: Optional[str] = None) -> LLMClient:
    key = api_key or default_api_key(base_url)
    if not key:
        raise RuntimeError(
            "No API key — set AALTO_API_KEY (Aalto AI API, the default "
            "gateway) or AALTO_LLM_KEY / OPENROUTER_API_KEY (with "
            "--base-url), or pass --api-key.")
    if not is_aalto_endpoint(base_url):
        print(
            f"[llm] WARNING: {base_url} is not an Aalto-hosted endpoint. "
            "A thesis draft is unpublished material — Aalto policy says not "
            "to send unpublished, confidential, or personal data to public "
            "AI services. Use the Aalto AI API (default) or the Aalto LLM "
            "Gateway instead.",
            file=sys.stderr)
    return LLMClient(base_url, key)


def extract_json(text: str) -> Optional[dict]:
    """Parse strict JSON, with a fallback to the first {...} block."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None
