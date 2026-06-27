# Velora — Autonomous AI Agent for CROO Network

Velora is a production-grade autonomous AI agent that earns real USDC by executing tasks on the [CROO Network](https://croo.network) — the decentralized agent commerce platform.

## What Velora Does

Velora connects to CROO as a *provider agent*. It:

1. Listens for incoming paid orders via WebSocket
2. Auto-accepts negotiations within concurrency limits
3. Routes tasks to specialized skills (research, coding, analysis, content, etc.)
4. Delivers results on-chain
5. Earns USDC automatically — 24/7

## Architecture

```
velora/
├── core/
│   ├── config.py          # All settings via env vars
│   ├── logger.py          # Structured JSON logging
│   └── ai_engine.py       # Multi-provider LLM with fallback chain
├── croo/
│   ├── client.py          # CROO SDK wrapper (retries, logging)
│   └── provider.py        # Provider runtime (WebSocket event loop)
├── skills/
│   ├── base.py            # BaseSkill abstract class
│   ├── router.py          # Skill routing (service_id → keyword → AI → fallback)
│   ├── research.py        # Deep research with web grounding
│   ├── coding.py          # Code generation, debugging, technical writing
│   ├── analysis.py        # Data analysis, business planning, startup validation
│   └── content.py         # Content creation, summarization, reasoning, planning
├── api/
│   └── server.py          # FastAPI server + health/status/admin endpoints
└── tests/                 # pytest unit tests
```

## Quick Start

### 1. Register on CROO

- Go to https://agent.croo.network
- Create an account (wallet / Google / email)
- Register your agent → get `Agent ID` and `API Key (croo_sk_...)`
- Add services (see CROO Deployment Guide below)

### 2. Clone and Configure

```bash
git clone https://github.com/YOUR_USERNAME/velora.git
cd velora
cp .env.example .env
# Edit .env with your CROO keys and at least one AI provider key
```

### 3. Run with Docker (recommended)

```bash
docker compose up -d
```

### 4. Run locally

```bash
pip install -r requirements.txt
python -m velora.main
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `CROO_SDK_KEY` | ✅ | `croo_sk_...` from agent.croo.network |
| `CROO_AGENT_ID` | ✅ | Agent ID from CROO dashboard |
| `SECRET_KEY` | ✅ | Min 32 chars, any random string |
| `OPENAI_API_KEY` | At least one AI key | OpenAI API key |
| `GROQ_API_KEY` | At least one AI key | Groq API key |
| `ANTHROPIC_API_KEY` | At least one AI key | Anthropic API key |
| `SERPER_API_KEY` | Recommended | Powers the Research skill |

See `.env.example` for the full list.

## Skills

| Skill | CROO Service Name | Description |
|---|---|---|
| research | "Deep Research" | Web search + AI synthesis reports |
| coding | "Code Generation" | Python, TypeScript, any language |
| coding (debug) | "Debugging" | Bug analysis and fixes |
| technical_writing | "Technical Writing" | Docs, READMEs, API guides |
| data_analysis | "Data Analysis" | Patterns, insights, statistics |
| business_planning | "Business Strategy" | Market analysis, planning |
| startup_validation | "Startup Validation" | PMF, market sizing, viability |
| content_creation | "Content Creation" | Blog posts, copy, social |
| summarization | "Summarization" | Documents, articles, meetings |
| reasoning | "Reasoning" | Complex problem solving |
| planning | "Project Planning" | Roadmaps, execution plans |
| automation | "Automation Design" | Workflows, API integrations |

## Adding a New Skill

```python
# velora/skills/my_skill.py
from velora.skills.base import BaseSkill, SkillResult

class MySkill(BaseSkill):
    name = "my_skill"
    description = "What this skill does"
    keywords = ["keyword1", "keyword2"]

    async def execute(self, requirements, order_id):
        task = self._get_task_text(requirements)
        # ... your logic ...
        return SkillResult(success=True, content="result", skill_name=self.name)
```

Then register it in `velora/skills/router.py` inside `_register_all()`.

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Agent info |
| `/health` | GET | Health check (used by Docker/Render) |
| `/status` | GET | Full status: CROO, skills, uptime |
| `/admin/orders` | GET | Active orders (requires API key) |
| `/admin/restart-provider` | POST | Hot restart provider (requires API key) |

## Tests

```bash
pytest velora/tests/ -v --cov=velora
```

## Deploy to Render

See `CROO_DEPLOYMENT.md` for step-by-step instructions.

## Built by

Emmanuel Ene Rejoice Gideon — MUTYINT Nigeria 🇳🇬
