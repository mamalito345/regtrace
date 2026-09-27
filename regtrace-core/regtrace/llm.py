"""
regtrace.llm
~~~~~~~~~~~~
LLM abstraction for policy interpretation and semantic binding proposals.

The LLM may interpret policy text and propose mappings, but it never decides
PASS, FAIL, or UNKNOWN. Final verification remains deterministic.
"""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any

from pydantic import ValidationError

from regtrace.models.constraint import PolicySpec


class LLMProvider(ABC):
    @abstractmethod
    def complete(
        self,
        system: str,
        user: str,
    ) -> str:
        """Return model text for one request."""


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        try:
            import openai
        except ImportError as exc:
            raise RuntimeError(
                "Install the 'openai' package "
                "to use OpenAIProvider."
            ) from exc

        key = (
            api_key
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("LLM_API_KEY")
        )

        if not key:
            raise RuntimeError(
                "No LLM API key found. "
                "Set OPENAI_API_KEY or LLM_API_KEY."
            )

        url = (
            base_url
            or os.environ.get("LLM_API_BASE")
        )

        self._model = (
            model
            or os.environ.get(
                "LLM_MODEL",
                "gpt-4o-mini",
            )
        )

        kwargs: dict[str, Any] = {
            "api_key": key,
        }

        if url:
            kwargs["base_url"] = url

        self._client = openai.OpenAI(
            **kwargs
        )

    def complete(
        self,
        system: str,
        user: str,
    ) -> str:
        response = (
            self._client
            .chat
            .completions
            .create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": system,
                    },
                    {
                        "role": "user",
                        "content": user,
                    },
                ],
                temperature=0,
            )
        )

        return (
            response
            .choices[0]
            .message
            .content
            or ""
        )


class FakeLLMProvider(LLMProvider):
    def __init__(
        self,
        response: str,
    ) -> None:
        self._response = response

    def complete(
        self,
        system: str,
        user: str,
    ) -> str:
        return self._response


def default_provider() -> LLMProvider:
    return OpenAIProvider()


_POLICY_COMPILER_SYSTEM = """\
You are a policy analysis assistant. Convert the policy text into JSON only.

Schema:
{
  "policy_id": "string",
  "policy_title": "string",
  "explanation": "string",
  "constraints": [
    {
      "id": "string",
      "type": "require_before",
      "description": "string",
      "severity": "required" or "recommended",
      "condition": {
        "name": "snake_case_concept",
        "description": "string"
      },
      "action": {
        "name": "snake_case_concept",
        "description": "string"
      }
    }
  ]
}

Rules:
- output JSON only
- supported constraint type is only "require_before"
- use generic semantic concept names, never source-code identifiers
- use "required" unless the policy explicitly says should/recommended
- create one constraint per distinct requirement
- do not invent requirements
- do not claim legal compliance
"""

_EXPLAIN_SYSTEM = """\
You are a developer-oriented policy advisor.

Given a feature description and policy text, explain in 3-5 concise bullet points:

- which stated policy requirements are relevant
- what the developer must account for technically
- what evidence or checks matter

Do not output PASS, FAIL, UNKNOWN, or any compliance verdict.
Do not claim legal compliance.
"""

_PLAN_SYSTEM = """\
You are a technical constraints advisor.

Given a feature description and policy text, produce at most 6 numbered technical
constraints the implementation should satisfy.

One sentence per item, starting with a verb.

Do not generate code.
Do not output a compliance verdict.
"""

_BINDING_SYSTEM = """\
You are a code semantics advisor.

Map each supplied semantic policy concept to zero or more identifiers from the
supplied code inventory.

Rules:
- use only identifiers present in the inventory
- never invent an identifier
- if uncertain, use an empty list
- return every requested concept as a key
- output JSON only in this shape:
  {"concept_name": ["identifier", ...]}
"""


class PolicyCompilerError(Exception):
    pass


class PolicyCompiler:
    def __init__(
        self,
        provider: LLMProvider,
    ) -> None:
        self._provider = provider

    def compile(
        self,
        policy_text: str,
        policy_id: str = "P-auto",
    ) -> PolicySpec:
        raw = self._provider.complete(
            _POLICY_COMPILER_SYSTEM,
            policy_text,
        ).strip()

        raw = _strip_code_fence(raw)

        try:
            data = json.loads(raw)

        except json.JSONDecodeError as exc:
            raise PolicyCompilerError(
                "LLM returned invalid JSON: "
                f"{exc}. Raw output: {raw[:500]}"
            ) from exc

        if not isinstance(data, dict):
            raise PolicyCompilerError(
                "LLM policy output must be "
                "a JSON object."
            )

        data.setdefault(
            "policy_id",
            policy_id,
        )

        try:
            return PolicySpec.model_validate(
                data
            )

        except ValidationError as exc:
            raise PolicyCompilerError(
                "LLM output failed schema "
                f"validation: {exc}"
            ) from exc


def explain(
    feature_intent: str,
    policy_text: str,
    provider: LLMProvider,
) -> str:
    user = (
        f"Feature:\n{feature_intent}\n\n"
        f"Policy:\n{policy_text}"
    )

    return provider.complete(
        _EXPLAIN_SYSTEM,
        user,
    ).strip()


def plan(
    feature_intent: str,
    policy_text: str,
    provider: LLMProvider,
) -> str:
    user = (
        f"Feature:\n{feature_intent}\n\n"
        f"Policy:\n{policy_text}"
    )

    return provider.complete(
        _PLAN_SYSTEM,
        user,
    ).strip()


class BindingProposalError(Exception):
    pass


def propose_bindings(
    concepts: list[str],
    code_inventory: dict[str, list[str]],
    provider: LLMProvider,
    feature_intent: str = "",
) -> dict[str, list[str]]:
    all_known: set[str] = set()

    for identifiers in code_inventory.values():
        all_known.update(
            identifiers
        )

    user = (
        "Feature intent:\n"
        f"{feature_intent or '<not provided>'}"
        "\n\nConcepts to map:\n"
        f"{json.dumps(concepts)}"
        "\n\nCode identifier inventory:\n"
        f"{json.dumps(code_inventory, indent=2)}"
    )

    raw = provider.complete(
        _BINDING_SYSTEM,
        user,
    ).strip()

    raw = _strip_code_fence(raw)

    try:
        proposed = json.loads(raw)

    except json.JSONDecodeError as exc:
        raise BindingProposalError(
            f"LLM returned invalid JSON: {exc}"
        ) from exc

    if not isinstance(proposed, dict):
        raise BindingProposalError(
            "LLM binding output must be "
            "a JSON object."
        )

    validated: dict[
        str,
        list[str],
    ] = {}

    for concept in concepts:
        aliases = proposed.get(
            concept,
            [],
        )

        if not isinstance(
            aliases,
            list,
        ):
            aliases = []

        safe: list[str] = []

        for alias in aliases:
            if (
                isinstance(alias, str)
                and alias in all_known
                and alias not in safe
            ):
                safe.append(alias)

        validated[concept] = safe

    return validated


def _strip_code_fence(
    text: str,
) -> str:
    if not text.startswith("```"):
        return text

    lines = text.splitlines()

    if (
        lines
        and lines[0].startswith("```")
    ):
        lines = lines[1:]

    if (
        lines
        and lines[-1].startswith("```")
    ):
        lines = lines[:-1]

    return "\n".join(
        lines
    ).strip()