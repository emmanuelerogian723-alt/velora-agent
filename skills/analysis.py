"""
Velora Skill — Data Analysis, Business Planning, Startup Validation
"""
from __future__ import annotations

from typing import Any, Dict

from velora.core.ai_engine import AIMessage, ai_engine
from velora.core.logger import get_logger
from velora.skills.base import BaseSkill, SkillResult

log = get_logger("velora.skills.analysis")

DATA_ANALYSIS_SYSTEM = """You are Velora, a senior data analyst and statistician.

Rules:
- Identify patterns, trends, and anomalies in the data
- Use statistical reasoning where appropriate
- Present findings clearly with supporting evidence from the data
- Provide actionable insights and recommendations
- Structure: Summary → Findings → Insights → Recommendations
- If data is insufficient, state what additional data would help
"""

BUSINESS_SYSTEM = """You are Velora, a McKinsey-level business strategy advisor.

Rules:
- Apply frameworks: SWOT, Porter's 5 Forces, Business Model Canvas, TAM/SAM/SOM
- Ground analysis in market realities
- Be direct about risks and challenges
- Provide actionable next steps
- Structure: Executive Summary → Market Analysis → Strategy → Action Plan → Risks
"""

STARTUP_SYSTEM = """You are Velora, a startup advisor with experience from Y Combinator, a16z, and Sequoia.

Rules:
- Validate the problem-solution fit rigorously
- Assess market size (TAM/SAM/SOM) with realistic estimates
- Identify the unfair advantage / moat
- Evaluate team-market fit
- Be honest about fatal flaws — don't sugarcoat
- Structure: Problem Validation → Solution Fit → Market → Moat → Team → Risks → Verdict
"""

GENERAL_SYSTEM = """You are Velora, an expert analyst and advisor.

Provide a thorough, structured analysis with clear reasoning, evidence-based conclusions, and actionable recommendations.
"""


class DataAnalysisSkill(BaseSkill):
    name = "data_analysis"
    description = "Data analysis, pattern recognition, and insights"
    keywords = ["analyze", "analysis", "data", "statistics", "metrics", "patterns", "trends", "insights"]
    version = "1.0.0"

    async def execute(self, requirements: Dict[str, Any], order_id: str) -> SkillResult:
        task = self._get_task_text(requirements)
        data = requirements.get("data", "")

        content = f"Analysis Task: {task}\n"
        if data:
            content += f"\nData provided:\n{str(data)[:3000]}"

        messages = [AIMessage(role="user", content=content)]
        response = await ai_engine.complete(messages=messages, system_prompt=DATA_ANALYSIS_SYSTEM, max_tokens=4096)

        return SkillResult(success=True, content=response.content, skill_name=self.name,
                           metadata={"provider": response.provider.value})


class BusinessPlanningSkill(BaseSkill):
    name = "business_planning"
    description = "Business strategy, planning, and market analysis"
    keywords = ["business", "plan", "strategy", "market", "competitor", "revenue", "model", "go-to-market"]
    version = "1.0.0"

    async def execute(self, requirements: Dict[str, Any], order_id: str) -> SkillResult:
        task = self._get_task_text(requirements)
        messages = [AIMessage(role="user", content=f"Business Task: {task}\n\nProvide a comprehensive business strategy analysis.")]
        response = await ai_engine.complete(messages=messages, system_prompt=BUSINESS_SYSTEM, max_tokens=4096)
        return SkillResult(success=True, content=response.content, skill_name=self.name,
                           metadata={"provider": response.provider.value})


class StartupValidationSkill(BaseSkill):
    name = "startup_validation"
    description = "Startup idea validation, market sizing, PMF assessment"
    keywords = ["startup", "validate", "validation", "idea", "pmf", "product market fit", "venture", "pitch"]
    version = "1.0.0"

    async def execute(self, requirements: Dict[str, Any], order_id: str) -> SkillResult:
        task = self._get_task_text(requirements)
        messages = [AIMessage(role="user", content=f"Startup to validate: {task}\n\nProvide a rigorous startup validation report.")]
        response = await ai_engine.complete(messages=messages, system_prompt=STARTUP_SYSTEM, max_tokens=4096)
        return SkillResult(success=True, content=response.content, skill_name=self.name,
                           metadata={"provider": response.provider.value})
