"""
Velora — Skill Router
Maps CROO service IDs and task text to the right skill.
Falls back to the General skill if no match found.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Type

from core.ai_engine import AIMessage, ai_engine
from core.logger import get_logger
from skills.base import BaseSkill, SkillResult

log = get_logger("velora.skills.router")


class GeneralSkill(BaseSkill):
    """Catch-all skill that handles any task intelligently."""
    name = "general"
    description = "General-purpose intelligent task handler"
    keywords = []
    version = "1.0.0"

    SYSTEM = """You are Velora, a highly capable autonomous AI agent.

You can handle any professional task: research, analysis, writing, coding, planning, and more.

Rules:
- Deliver a complete, high-quality response
- Structure your output clearly
- If the task is ambiguous, make your best interpretation and state it
- Never produce empty or trivial responses
- Always provide genuine value
"""

    async def execute(self, requirements: Dict[str, Any], order_id: str) -> SkillResult:
        task = self._get_task_text(requirements)
        messages = [AIMessage(role="user", content=f"Task: {task}\n\nPlease complete this task thoroughly.")]
        response = await ai_engine.complete(messages=messages, system_prompt=self.SYSTEM, max_tokens=4096)
        return SkillResult(success=True, content=response.content, skill_name=self.name,
                           metadata={"provider": response.provider.value, "routing": "general_fallback"})


class SkillRouter:
    """
    Routes an incoming CROO order to the best matching skill.

    Routing priority:
      1. Exact service_id match (from CROO dashboard service name)
      2. Keyword match against task text
      3. AI-assisted routing for ambiguous tasks
      4. General fallback
    """

    def __init__(self) -> None:
        self._skills: Dict[str, BaseSkill] = {}
        self._register_all()

    def _register_all(self) -> None:
        from skills.research import ResearchSkill
        from skills.coding import CodingSkill, TechnicalWritingSkill
        from skills.analysis import DataAnalysisSkill, BusinessPlanningSkill, StartupValidationSkill
        from skills.content import (
            ContentCreationSkill, SummarizationSkill,
            ReasoningSkill, PlanningSkill, AutomationSkill,
        )

        skill_classes: List[Type[BaseSkill]] = [
            ResearchSkill,
            CodingSkill,
            TechnicalWritingSkill,
            DataAnalysisSkill,
            BusinessPlanningSkill,
            StartupValidationSkill,
            ContentCreationSkill,
            SummarizationSkill,
            ReasoningSkill,
            PlanningSkill,
            AutomationSkill,
            GeneralSkill,
        ]

        for cls in skill_classes:
            instance = cls()
            self._skills[instance.name] = instance
            log.info("Skill registered", extra={"skill": instance.name})

    def register(self, skill: BaseSkill) -> None:
        """Register a custom skill at runtime."""
        self._skills[skill.name] = skill
        log.info("Custom skill registered", extra={"skill": skill.name})

    async def execute(self, service_id: str, requirements: Dict[str, Any], order_id: str) -> str:
        """
        Route the task to the best skill and return the delivery text.
        """
        skill = await self._route(service_id, requirements)
        log.info(
            "Routing to skill",
            extra={"order_id": order_id, "skill": skill.name, "service_id": service_id},
        )

        try:
            result: SkillResult = await skill.execute(requirements, order_id)
        except Exception as e:
            log.error("Skill execution error", extra={"skill": skill.name, "error": str(e)}, exc_info=True)
            result = SkillResult(
                success=False,
                content="",
                skill_name=skill.name,
                error=str(e),
            )

        return result.to_delivery_text()

    async def _route(self, service_id: str, requirements: Dict[str, Any]) -> BaseSkill:
        """Multi-stage routing: service_id → keywords → AI → fallback."""

        # Stage 1: direct service_id match (normalized)
        normalized = self._normalize(service_id)
        if normalized in self._skills:
            return self._skills[normalized]

        # Stage 2: partial service_id match
        for skill_name, skill in self._skills.items():
            if skill_name == "general":
                continue
            if skill_name in normalized or normalized in skill_name:
                return skill

        # Stage 3: keyword match on task text
        task_text = self._get_task_text(requirements).lower()
        best_skill: Optional[BaseSkill] = None
        best_score = 0

        for skill in self._skills.values():
            if skill.name == "general":
                continue
            score = sum(1 for kw in skill.keywords if kw in task_text)
            if score > best_score:
                best_score = score
                best_skill = skill

        if best_skill and best_score > 0:
            return best_skill

        # Stage 4: AI-assisted routing for ambiguous tasks
        ai_skill = await self._ai_route(task_text)
        if ai_skill:
            return ai_skill

        # Stage 5: General fallback
        return self._skills["general"]

    async def _ai_route(self, task_text: str) -> Optional[BaseSkill]:
        """Ask the AI to pick the best skill for the task."""
        skill_list = "\n".join(
            f"- {name}: {skill.description}"
            for name, skill in self._skills.items()
            if name != "general"
        )
        try:
            messages = [
                AIMessage(
                    role="user",
                    content=f"""Given this task: "{task_text[:500]}"

Available skills:
{skill_list}

Reply with ONLY the skill name that best matches. Nothing else.""",
                )
            ]
            response = await ai_engine.complete(messages=messages, max_tokens=20, temperature=0.0)
            skill_name = response.content.strip().lower().replace(" ", "_")
            if skill_name in self._skills:
                return self._skills[skill_name]
        except Exception:
            pass
        return None

    def _normalize(self, s: str) -> str:
        return re.sub(r"[^a-z0-9_]", "_", s.lower()).strip("_")

    def _get_task_text(self, requirements: Dict[str, Any]) -> str:
        return (
            requirements.get("task")
            or requirements.get("text")
            or requirements.get("query")
            or requirements.get("prompt")
            or str(requirements)
        )

    @property
    def available_skills(self) -> List[str]:
        return list(self._skills.keys())


# Singleton
skill_router = SkillRouter()
