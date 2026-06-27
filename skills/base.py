"""
Velora — Skill Base Class
All skills inherit from BaseSkill.  Adding a new skill = subclass + register.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SkillResult:
    success: bool
    content: str
    skill_name: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_delivery_text(self) -> str:
        if not self.success:
            return f"[Velora Error] Skill '{self.skill_name}' failed: {self.error}"
        return self.content


class BaseSkill(ABC):
    """
    Abstract base for all Velora skills.

    Each skill:
      - declares `name` (matches CROO service name keywords)
      - declares `keywords` for routing
      - implements `execute(requirements)`
    """

    name: str = "base"
    description: str = ""
    keywords: List[str] = []
    version: str = "1.0.0"

    @abstractmethod
    async def execute(self, requirements: Dict[str, Any], order_id: str) -> SkillResult:
        """Execute the skill. Must return a SkillResult."""
        ...

    def _get_task_text(self, requirements: Dict[str, Any]) -> str:
        """Helper: extract the primary task description from requirements."""
        return (
            requirements.get("task")
            or requirements.get("text")
            or requirements.get("query")
            or requirements.get("prompt")
            or str(requirements)
        )
