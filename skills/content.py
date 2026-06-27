"""
Velora Skill — Content Creation, Summarization, Reasoning, Multi-step Planning
"""
from __future__ import annotations

from typing import Any, Dict

from core.ai_engine import AIMessage, ai_engine
from core.logger import get_logger
from skills.base import BaseSkill, SkillResult

log = get_logger("velora.skills.content")

CONTENT_SYSTEM = """You are Velora, a professional content creator and copywriter.

Rules:
- Match tone to the specified audience and platform
- Create engaging, original content
- Maintain consistent voice and style
- Optimize for readability and impact
- Always deliver the full content (not a template or outline unless requested)
"""

SUMMARIZATION_SYSTEM = """You are Velora, an expert at distilling complex information.

Rules:
- Capture all key points without losing critical nuance
- Preserve the original author's intent
- Structure by importance (most critical first)
- Use clear, concise language
- Note: [Summary of X words] at the end
"""

REASONING_SYSTEM = """You are Velora, a rigorous analytical thinker.

Rules:
- Show your reasoning step by step
- Identify assumptions explicitly
- Consider alternative viewpoints
- Evaluate evidence quality
- State your conclusion clearly with confidence level
- Highlight where more information is needed
"""

PLANNING_SYSTEM = """You are Velora, a project planning and execution expert.

Rules:
- Break complex goals into concrete, actionable steps
- Assign realistic timeframes to each step
- Identify dependencies between tasks
- Flag potential blockers and mitigations
- Include success metrics for each phase
- Format: Goal → Phases → Tasks → Timeline → Risks → Success Metrics
"""

AUTOMATION_SYSTEM = """You are Velora, an automation and workflow expert.

Rules:
- Design efficient, reliable automation workflows
- Identify the best tools/APIs for each step
- Handle error cases explicitly
- Provide implementation code or pseudocode
- Consider scalability and maintenance
"""


class ContentCreationSkill(BaseSkill):
    name = "content_creation"
    description = "Blog posts, copy, social media, marketing content"
    keywords = ["content", "write", "blog", "post", "article", "copy", "marketing", "social", "email"]
    version = "1.0.0"

    async def execute(self, requirements: Dict[str, Any], order_id: str) -> SkillResult:
        task = self._get_task_text(requirements)
        tone = requirements.get("tone", "professional")
        audience = requirements.get("audience", "general")
        platform = requirements.get("platform", "")

        content = f"Content Task: {task}\nTone: {tone}\nAudience: {audience}"
        if platform:
            content += f"\nPlatform: {platform}"

        messages = [AIMessage(role="user", content=content)]
        response = await ai_engine.complete(messages=messages, system_prompt=CONTENT_SYSTEM, max_tokens=4096)
        return SkillResult(success=True, content=response.content, skill_name=self.name,
                           metadata={"provider": response.provider.value})


class SummarizationSkill(BaseSkill):
    name = "summarization"
    description = "Summarize documents, articles, meetings, reports"
    keywords = ["summarize", "summary", "tldr", "condense", "brief", "overview", "abstract"]
    version = "1.0.0"

    async def execute(self, requirements: Dict[str, Any], order_id: str) -> SkillResult:
        task = self._get_task_text(requirements)
        text_to_summarize = requirements.get("content") or requirements.get("text") or task
        length = requirements.get("length", "medium")

        messages = [AIMessage(role="user", content=f"Please summarize the following (target length: {length}):\n\n{text_to_summarize}")]
        response = await ai_engine.complete(messages=messages, system_prompt=SUMMARIZATION_SYSTEM, max_tokens=2048)
        return SkillResult(success=True, content=response.content, skill_name=self.name,
                           metadata={"provider": response.provider.value})


class ReasoningSkill(BaseSkill):
    name = "reasoning"
    description = "Complex reasoning, problem-solving, decision analysis"
    keywords = ["reason", "reasoning", "think", "analyze", "problem", "solve", "decision", "evaluate", "should"]
    version = "1.0.0"

    async def execute(self, requirements: Dict[str, Any], order_id: str) -> SkillResult:
        task = self._get_task_text(requirements)
        messages = [AIMessage(role="user", content=f"Problem to reason through:\n\n{task}")]
        response = await ai_engine.complete(messages=messages, system_prompt=REASONING_SYSTEM, max_tokens=4096, temperature=0.1)
        return SkillResult(success=True, content=response.content, skill_name=self.name,
                           metadata={"provider": response.provider.value})


class PlanningSkill(BaseSkill):
    name = "planning"
    description = "Project planning, roadmaps, execution strategies"
    keywords = ["plan", "planning", "roadmap", "project", "execute", "strategy", "steps", "timeline", "schedule"]
    version = "1.0.0"

    async def execute(self, requirements: Dict[str, Any], order_id: str) -> SkillResult:
        task = self._get_task_text(requirements)
        messages = [AIMessage(role="user", content=f"Create a detailed execution plan for:\n\n{task}")]
        response = await ai_engine.complete(messages=messages, system_prompt=PLANNING_SYSTEM, max_tokens=4096)
        return SkillResult(success=True, content=response.content, skill_name=self.name,
                           metadata={"provider": response.provider.value})


class AutomationSkill(BaseSkill):
    name = "automation"
    description = "Workflow automation, API integrations, process design"
    keywords = ["automate", "automation", "workflow", "integrate", "integration", "api", "process", "pipeline"]
    version = "1.0.0"

    async def execute(self, requirements: Dict[str, Any], order_id: str) -> SkillResult:
        task = self._get_task_text(requirements)
        messages = [AIMessage(role="user", content=f"Design an automation for:\n\n{task}")]
        response = await ai_engine.complete(messages=messages, system_prompt=AUTOMATION_SYSTEM, max_tokens=4096)
        return SkillResult(success=True, content=response.content, skill_name=self.name,
                           metadata={"provider": response.provider.value})
