"""
Velora — Unit Tests for Skills
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from skills.base import SkillResult
from skills.router import SkillRouter, GeneralSkill
from skills.research import ResearchSkill
from skills.coding import CodingSkill
from skills.analysis import DataAnalysisSkill, BusinessPlanningSkill
from skills.content import SummarizationSkill, PlanningSkill


MOCK_AI_RESPONSE = MagicMock()
MOCK_AI_RESPONSE.content = "This is a mock AI response with detailed content."
MOCK_AI_RESPONSE.provider = MagicMock()
MOCK_AI_RESPONSE.provider.value = "openai"
MOCK_AI_RESPONSE.prompt_tokens = 100
MOCK_AI_RESPONSE.completion_tokens = 200


@pytest.fixture
def mock_ai():
    with patch("velora.core.ai_engine.ai_engine.complete", new_callable=AsyncMock) as mock:
        mock.return_value = MOCK_AI_RESPONSE
        yield mock


@pytest.mark.asyncio
async def test_general_skill_executes(mock_ai):
    skill = GeneralSkill()
    result = await skill.execute({"text": "Explain quantum computing"}, "order-001")
    assert result.success is True
    assert len(result.content) > 0
    assert result.skill_name == "general"


@pytest.mark.asyncio
async def test_coding_skill_detects_debug_mode(mock_ai):
    skill = CodingSkill()
    req = {"text": "Debug this Python traceback: KeyError on line 42"}
    result = await skill.execute(req, "order-002")
    assert result.success is True
    assert result.metadata.get("mode") == "debug"


@pytest.mark.asyncio
async def test_coding_skill_detects_coding_mode(mock_ai):
    skill = CodingSkill()
    req = {"text": "Write a FastAPI endpoint for user registration"}
    result = await skill.execute(req, "order-003")
    assert result.success is True
    assert result.metadata.get("mode") == "coding"


@pytest.mark.asyncio
async def test_research_skill_with_no_serper(mock_ai):
    with patch("velora.core.config.settings.SERPER_API_KEY", None):
        skill = ResearchSkill()
        result = await skill.execute({"text": "AI trends 2026"}, "order-004")
        assert result.success is True


@pytest.mark.asyncio
async def test_summarization_skill(mock_ai):
    skill = SummarizationSkill()
    req = {"content": "Long article text " * 100, "length": "short"}
    result = await skill.execute(req, "order-005")
    assert result.success is True


@pytest.mark.asyncio
async def test_skill_router_keyword_routing():
    router = SkillRouter()
    # research keywords
    requirements = {"text": "research the AI market in Africa"}
    skill = await router._route("unknown_service", requirements)
    assert skill.name in ["research", "general"]


@pytest.mark.asyncio
async def test_skill_router_direct_service_id():
    router = SkillRouter()
    skill = await router._route("coding", {"text": "write python code"})
    assert skill.name == "coding"


@pytest.mark.asyncio
async def test_skill_router_fallback_to_general():
    router = SkillRouter()
    # Completely ambiguous task with no keywords
    with patch.object(router, "_ai_route", new_callable=AsyncMock, return_value=None):
        skill = await router._route("xyz_unknown_service_123", {"text": "qqq zzz yyy"})
        assert skill.name == "general"


@pytest.mark.asyncio
async def test_skill_result_delivery_text():
    result_ok = SkillResult(success=True, content="Great analysis here", skill_name="research")
    assert result_ok.to_delivery_text() == "Great analysis here"

    result_fail = SkillResult(success=False, content="", skill_name="coding", error="API timeout")
    assert "coding" in result_fail.to_delivery_text()
    assert "API timeout" in result_fail.to_delivery_text()


@pytest.mark.asyncio
async def test_router_execute_returns_string(mock_ai):
    router = SkillRouter()
    result_str = await router.execute(
        service_id="planning",
        requirements={"text": "Plan a product launch"},
        order_id="order-999",
    )
    assert isinstance(result_str, str)
    assert len(result_str) > 0


@pytest.mark.asyncio
async def test_business_planning_skill(mock_ai):
    skill = BusinessPlanningSkill()
    result = await skill.execute({"text": "Build a fintech app in Nigeria"}, "order-010")
    assert result.success is True
    assert result.skill_name == "business_planning"
