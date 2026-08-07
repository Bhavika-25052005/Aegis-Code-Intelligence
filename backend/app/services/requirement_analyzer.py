import json
import logging
import re

from app.models.backlog import Feature, UserStory
from app.services.claude_runner import ClaudeRunner

logger = logging.getLogger(__name__)


class RequirementAnalysisError(Exception):
    pass


class RequirementAnalyzer:
    """
    Converts a user story into a structured implementation contract.
    Claude analyzes the requirement but is not allowed to edit source code.
    """

    def __init__(
        self,
        workspace_path: str,
        max_budget_usd: float = 1.0,
    ):
        self.runner = ClaudeRunner(
            workspace_path=workspace_path,
            max_budget_usd=max_budget_usd,
            allowed_tools="",
        )

    async def analyze(
        self,
        feature: Feature,
        story: UserStory,
    ) -> dict:
        prompt = self._build_prompt(feature, story)
        result = await self.runner.execute(prompt)

        if not result.success:
            raise RequirementAnalysisError(
                result.error or "Requirement analysis failed."
            )

        logger.info(f"Requirement analysis raw output (first 800): {result.output[:800]}")

        try:
            return self._parse_json(result.output)
        except Exception as exc:
            raise RequirementAnalysisError(
                f"Claude returned invalid analysis JSON: {exc}. "
                f"Raw output (first 300): {result.output[:300]!r}"
            ) from exc

    def _build_prompt(
        self,
        feature: Feature,
        story: UserStory,
    ) -> str:
        return f"""
You are the Requirement Intelligence component of Aegis,
an AI-driven development and quality engineering platform.

Your job is NOT to implement code.
Your job is to transform a software user story into a
clear implementation and testing contract.

IMPORTANT: All the context you need is provided below.
Do NOT use any tools. Do NOT read any files.
Reason purely from the text provided and reply directly with JSON.

FEATURE
Title:
{feature.title}

Description:
{feature.description or "Not provided"}

USER STORY
Title:
{story.title}

Description:
{story.description or "Not provided"}

EXISTING ACCEPTANCE CRITERIA
{story.acceptance_criteria or "Not provided"}

Analyze the requirement and return:
1. summary
2. testable acceptance criteria
3. functional rules
4. edge cases
5. assumptions
6. dependencies
7. ambiguities
8. risks
9. questions that should be resolved before coding
10. overall risk level

Rules:
- Do NOT use tools or read files.
- Do NOT modify files.
- Do NOT generate implementation code.
- Do NOT invent business facts.
- Keep assumptions explicitly labelled as assumptions.
- Acceptance criteria must be testable.
- Include boundary conditions when relevant.
- Consider null, empty, invalid and extreme inputs where relevant.
- risk_level must be one of: low, medium, high, critical
- Return ONLY valid JSON. No prose before or after the JSON.

Use exactly this structure:
{{
  "summary": "short explanation",
  "acceptance_criteria": ["criterion"],
  "functional_rules": ["rule"],
  "edge_cases": ["edge case"],
  "assumptions": ["assumption"],
  "dependencies": ["dependency"],
  "ambiguities": ["ambiguity"],
  "risks": ["risk"],
  "questions": ["question"],
  "risk_level": "medium"
}}
""".strip()

    @staticmethod
    def _parse_json(output: str) -> dict:
        if not output:
            raise ValueError("Claude returned an empty response.")

        cleaned = output.strip()

        # Unwrap the Claude CLI envelope if present.
        # The CLI wraps responses as {"type":"result","result":"<actual text>", ...}
        try:
            envelope = json.loads(cleaned)
            if isinstance(envelope, dict) and "result" in envelope:
                inner = envelope["result"]
                if isinstance(inner, str) and inner.strip():
                    cleaned = inner.strip()
                elif not inner:
                    raise ValueError(
                        "Claude CLI envelope has an empty 'result' field. "
                        "Claude may have used tools without producing a final text response."
                    )
        except (json.JSONDecodeError, ValueError):
            pass

        # Strip markdown code fence if present.
        fenced = re.search(
            r"```(?:json)?\s*(\{.*\})\s*```",
            cleaned,
            re.DOTALL | re.IGNORECASE,
        )
        if fenced:
            cleaned = fenced.group(1)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start == -1 or end == -1:
                raise ValueError("No JSON object found.")
            data = json.loads(cleaned[start:end + 1])

        if not isinstance(data, dict):
            raise ValueError("Expected JSON object.")

        # If we got the envelope dict itself (not unwrapped above), fail clearly.
        if "result" in data and "type" in data and "summary" not in data:
            raise ValueError(
                "Received Claude CLI envelope instead of analysis JSON. "
                "The 'result' field was empty or not extracted."
            )

        expected_list_fields = [
            "acceptance_criteria",
            "functional_rules",
            "edge_cases",
            "assumptions",
            "dependencies",
            "ambiguities",
            "risks",
            "questions",
        ]

        data.setdefault("summary", "")
        for field in expected_list_fields:
            value = data.get(field, [])
            if value is None:
                value = []
            if isinstance(value, str):
                value = [value]
            if not isinstance(value, list):
                value = []
            data[field] = [
                str(item)
                for item in value
                if str(item).strip()
            ]

        risk_level = str(data.get("risk_level", "medium")).lower()
        if risk_level not in {"low", "medium", "high", "critical"}:
            risk_level = "medium"
        data["risk_level"] = risk_level

        return data
