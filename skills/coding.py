"""
Velora Skill — Coding, Debugging & Technical Writing
"""
from __future__ import annotations

from typing import Any, Dict

from core.ai_engine import AIMessage, ai_engine
from core.logger import get_logger
from skills.base import BaseSkill, SkillResult

log = get_logger("velora.skills.coding")

CODING_SYSTEM = """You are Velora, a senior software engineer with 15+ years experience.

Specialties: Python, TypeScript, React, FastAPI, Node.js, SQL, Docker, system design.

Rules:
- Write clean, production-quality code with proper error handling
- Include docstrings and inline comments for complex logic
- Follow SOLID principles and language idioms
- Always include a brief explanation of what the code does
- For bugs: identify root cause, explain the fix, show corrected code
- Format code in proper markdown code blocks with language tags
"""

DEBUG_SYSTEM = """You are Velora, a debugging expert.

Rules:
- Identify the exact root cause of the bug
- Explain WHY it happens (not just what)
- Provide the corrected code
- Suggest how to prevent similar bugs
- Check for related issues in the surrounding code
"""

TECHNICAL_WRITING_SYSTEM = """You are Velora, a technical writer.

Rules:
- Write clear, precise technical documentation
- Use consistent terminology throughout
- Include examples where helpful
- Structure with proper headings and sections
- Tailor complexity to the stated audience level
"""


class CodingSkill(BaseSkill):
    name = "coding"
    description = "Code generation, debugging, and technical writing"
    keywords = [
        "code", "coding", "program", "script", "implement", "build", "develop",
        "debug", "fix", "bug", "error", "exception", "refactor",
        "api", "function", "class", "algorithm",
    ]
    version = "1.0.0"

    async def execute(self, requirements: Dict[str, Any], order_id: str) -> SkillResult:
        task = self._get_task_text(requirements)
        mode = self._detect_mode(task, requirements)

        log.info("Coding skill executing", extra={"order_id": order_id, "mode": mode, "task_preview": task[:100]})

        system_map = {
            "debug": DEBUG_SYSTEM,
            "technical_writing": TECHNICAL_WRITING_SYSTEM,
            "coding": CODING_SYSTEM,
        }
        system_prompt = system_map.get(mode, CODING_SYSTEM)

        language = requirements.get("language", "")
        context = requirements.get("context", "")
        code_snippet = requirements.get("code", "")

        user_content = f"Task: {task}\n"
        if language:
            user_content += f"Language: {language}\n"
        if context:
            user_content += f"Context: {context}\n"
        if code_snippet:
            user_content += f"\nExisting code:\n```\n{code_snippet}\n```\n"
        user_content += "\nPlease provide your complete solution."

        messages = [AIMessage(role="user", content=user_content)]
        response = await ai_engine.complete(
            messages=messages,
            system_prompt=system_prompt,
            max_tokens=4096,
            temperature=0.1,
        )

        return SkillResult(
            success=True,
            content=response.content,
            skill_name=self.name,
            metadata={"mode": mode, "provider": response.provider.value},
        )

    def _detect_mode(self, task: str, requirements: Dict) -> str:
        task_lower = task.lower()
        if any(w in task_lower for w in ["debug", "fix", "bug", "error", "traceback", "exception", "crash"]):
            return "debug"
        if any(w in task_lower for w in ["document", "readme", "docs", "write", "explain", "tutorial"]):
            return "technical_writing"
        return "coding"


class TechnicalWritingSkill(BaseSkill):
    name = "technical_writing"
    description = "Technical documentation, READMEs, API docs"
    keywords = ["document", "documentation", "readme", "api docs", "technical writing", "tutorial", "guide"]
    version = "1.0.0"

    async def execute(self, requirements: Dict[str, Any], order_id: str) -> SkillResult:
        task = self._get_task_text(requirements)

        messages = [AIMessage(role="user", content=f"Task: {task}\n\nProvide professional technical documentation.")]
        response = await ai_engine.complete(
            messages=messages,
            system_prompt=TECHNICAL_WRITING_SYSTEM,
            max_tokens=4096,
        )

        return SkillResult(
            success=True,
            content=response.content,
            skill_name=self.name,
            metadata={"provider": response.provider.value},
        )
