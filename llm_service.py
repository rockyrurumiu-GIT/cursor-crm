"""Local LLM abstraction for handoff AI features. Defaults to null provider (no-op)."""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Protocol


class LLMProvider(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class NullProvider:
    def complete(self, system: str, user: str) -> str:
        return ""


class OllamaProvider:
    def __init__(self, base_url: str, model: str, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def complete(self, system: str, user: str) -> str:
        import urllib.error
        import urllib.request

        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Ollama 请求失败: {exc}") from exc
        msg = data.get("message") or {}
        return str(msg.get("content") or "")


class OpenAICompatProvider:
    def __init__(self, base_url: str, model: str, timeout: float, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.api_key = api_key or os.environ.get("CRM_LLM_API_KEY", "local")

    def complete(self, system: str, user: str) -> str:
        import urllib.error
        import urllib.request

        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.1,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"OpenAI 兼容 API 请求失败: {exc}") from exc
        choices = data.get("choices") or []
        if not choices:
            return ""
        return str((choices[0].get("message") or {}).get("content") or "")


def _extract_json_block(text: str) -> Optional[dict]:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


class LLMService:
    def __init__(self, provider: Optional[LLMProvider] = None):
        self.provider = provider or _build_provider()

    @property
    def available(self) -> bool:
        return not isinstance(self.provider, NullProvider)

    def extract_structured(self, text: str, schema_hint: str) -> Dict[str, Any]:
        if not self.available:
            return {"ok": False, "error": "LLM 未配置", "data": {}}
        system = (
            "你是 ITO 外包销售助手。仅提取文中明确提到的信息，不得推测。"
            "必须输出合法 JSON，不要输出其他文字。"
        )
        user = f"JSON Schema 提示:\n{schema_hint}\n\n原文:\n{text[:8000]}"
        try:
            raw = self.provider.complete(system, user)
            parsed = _extract_json_block(raw) or {}
            return {"ok": True, "data": parsed, "raw": raw[:4000]}
        except RuntimeError as exc:
            return {"ok": False, "error": str(exc), "data": {}}

    def summarize_brief(self, context: str) -> Dict[str, Any]:
        if not self.available:
            return {"ok": False, "error": "LLM 未配置", "markdown": ""}
        system = (
            "你是 ITO 交付顾问。根据输入生成《项目启动前置需求书》Markdown。"
            "章节固定：## 背景、## 编制需求、## 技术栈、## 到岗计划、## 风险与待确认。"
            "仅基于给定事实，缺失处写「待确认」。"
        )
        try:
            md = self.provider.complete(system, context[:12000])
            return {"ok": True, "markdown": md.strip()}
        except RuntimeError as exc:
            return {"ok": False, "error": str(exc), "markdown": ""}

    def diff_checklist(self, brief_md: str, checklist: List[str]) -> Dict[str, Any]:
        if not self.available:
            return {"ok": False, "error": "LLM 未配置", "gaps": []}
        items = "\n".join(f"- {c}" for c in checklist)
        system = (
            "对比需求书与检查清单，输出 JSON 数组 gaps。"
            "每项: field, severity(high|medium|low), suggestion。"
            "仅 JSON，无其他文字。"
        )
        user = f"需求书:\n{brief_md[:8000]}\n\n检查清单:\n{items}"
        try:
            raw = self.provider.complete(system, user)
            parsed = _extract_json_block(raw)
            gaps = parsed if isinstance(parsed, list) else (parsed or {}).get("gaps", [])
            if not isinstance(gaps, list):
                gaps = []
            return {"ok": True, "gaps": gaps}
        except RuntimeError as exc:
            return {"ok": False, "error": str(exc), "gaps": []}


def _build_provider() -> LLMProvider:
    name = (os.environ.get("CRM_LLM_PROVIDER") or "null").strip().lower()
    timeout = float(os.environ.get("CRM_LLM_TIMEOUT") or "60")
    model = os.environ.get("CRM_LLM_MODEL") or "qwen3:8b"
    base = os.environ.get("CRM_LLM_BASE_URL") or "http://127.0.0.1:11434"
    if name == "ollama":
        return OllamaProvider(base, model, timeout)
    if name in ("openai_compat", "openai", "vllm"):
        return OpenAICompatProvider(base, model, timeout)
    return NullProvider()


_llm_singleton: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    global _llm_singleton
    if _llm_singleton is None:
        _llm_singleton = LLMService()
    return _llm_singleton
