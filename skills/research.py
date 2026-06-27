"""
Velora Skill — Deep Research
Uses web search + LLM synthesis to produce structured research reports.
"""
from __future__ import annotations

from typing import Any, Dict, List

import httpx

from core.ai_engine import AIMessage, ai_engine
from core.config import settings
from core.logger import get_logger
from skills.base import BaseSkill, SkillResult

log = get_logger("velora.skills.research")

SYSTEM_PROMPT = """You are Velora, an expert research analyst.

Your job is to produce comprehensive, factual, well-structured research reports.

Rules:
- Base your analysis on the web search results provided
- Structure reports with: Executive Summary, Key Findings, Analysis, Recommendations, Sources
- Never hallucinate facts not present in the search results
- Cite sources inline using [Source: URL] notation
- Write in clear professional prose
- If information is insufficient, state that explicitly
"""


class ResearchSkill(BaseSkill):
    name = "research"
    description = "Deep research with web search and AI synthesis"
    keywords = ["research", "deep research", "investigate", "analyze", "study", "report"]
    version = "1.0.0"

    async def execute(self, requirements: Dict[str, Any], order_id: str) -> SkillResult:
        task = self._get_task_text(requirements)
        depth = requirements.get("depth", "comprehensive")

        log.info("Research skill executing", extra={"order_id": order_id, "task_preview": task[:100]})

        # Step 1: Web search for grounding
        search_results = await self._web_search(task)

        # Step 2: AI synthesis
        search_context = self._format_search_results(search_results)

        messages = [
            AIMessage(
                role="user",
                content=f"""Research Task: {task}

Depth requested: {depth}

Web Search Results:
{search_context}

Please produce a comprehensive research report based on these findings."""
            )
        ]

        response = await ai_engine.complete(
            messages=messages,
            system_prompt=SYSTEM_PROMPT,
            max_tokens=4096,
            temperature=0.1,
        )

        return SkillResult(
            success=True,
            content=response.content,
            skill_name=self.name,
            metadata={
                "sources_count": len(search_results),
                "ai_provider": response.provider.value,
                "tokens_used": response.prompt_tokens + response.completion_tokens,
            },
        )

    async def _web_search(self, query: str, num_results: int = 8) -> List[Dict]:
        """Search using Serper API."""
        if not settings.SERPER_API_KEY:
            log.warning("No SERPER_API_KEY — skipping web search")
            return []

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://google.serper.dev/search",
                    headers={"X-API-KEY": settings.SERPER_API_KEY, "Content-Type": "application/json"},
                    json={"q": query, "num": num_results},
                )
                resp.raise_for_status()
                data = resp.json()

                results = []
                # Answer box
                if ab := data.get("answerBox"):
                    results.append({
                        "title": "Direct Answer",
                        "snippet": ab.get("answer") or ab.get("snippet", ""),
                        "url": ab.get("link", ""),
                    })
                # Organic results
                for r in data.get("organic", [])[:num_results]:
                    results.append({
                        "title": r.get("title", ""),
                        "snippet": r.get("snippet", ""),
                        "url": r.get("link", ""),
                        "date": r.get("date", ""),
                    })
                return results
        except Exception as e:
            log.warning("Web search failed", extra={"error": str(e)})
            return []

    def _format_search_results(self, results: List[Dict]) -> str:
        if not results:
            return "No web search results available."
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"[{i}] {r['title']}")
            lines.append(f"    URL: {r.get('url', 'N/A')}")
            lines.append(f"    {r.get('snippet', '')}")
            if r.get("date"):
                lines.append(f"    Date: {r['date']}")
            lines.append("")
        return "\n".join(lines)
