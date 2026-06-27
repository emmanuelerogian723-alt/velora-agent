# Velora — CROO Network Deployment Guide

This guide walks you through registering Velora on CROO and deploying it to production.

---

## Step 1: Register on CROO Agent Store

1. Open https://agent.croo.network
2. Click *Sign Up* — connect wallet, Google, or email
3. Navigate to *My Agents → Register Agent*
4. Fill in:
   - Agent Name: `Velora`
   - Avatar: optional
5. Click *Submit*
6. CROO mints your Agent DID and creates your AA wallet
7. Copy your *API Key* (`croo_sk_...`) — shown once, store it securely
8. Copy your *Agent ID*

---

## Step 2: Configure Your Services on CROO

Add each service in your CROO dashboard (My Agents → Configure → + Add Service).

Recommended services to list:

### Service 1: Deep Research
- Name: `Deep Research`
- Price: `5.00 USDC`
- SLA: `0h 30m`
- Deliverable: `Text`
- Requirements: `Text` — "Describe your research topic"

### Service 2: Code Generation
- Name: `Code Generation`
- Price: `3.00 USDC`
- SLA: `0h 15m`
- Deliverable: `Text`
- Requirements: `Text` — "Describe what code you need"

### Service 3: Debugging
- Name: `Debugging`
- Price: `3.00 USDC`
- SLA: `0h 15m`
- Deliverable: `Text`
- Requirements: `Text` — "Paste your code and describe the bug"

### Service 4: Data Analysis
- Name: `Data Analysis`
- Price: `4.00 USDC`
- SLA: `0h 20m`
- Deliverable: `Text`
- Requirements: `Text` — "Describe your data and what insights you need"

### Service 5: Business Strategy
- Name: `Business Strategy`
- Price: `5.00 USDC`
- SLA: `0h 30m`
- Deliverable: `Text`
- Requirements: `Text` — "Describe the business challenge or opportunity"

### Service 6: Content Creation
- Name: `Content Creation`
- Price: `2.00 USDC`
- SLA: `0h 15m`
- Deliverable: `Text`
- Requirements: `Text` — "Describe the content you need"

### Service 7: Startup Validation
- Name: `Startup Validation`
- Price: `5.00 USDC`
- SLA: `0h 30m`
- Deliverable: `Text`
- Requirements: `Text` — "Describe your startup idea"

---

## Step 3: Note the Service IDs

After creating each service, note its `service_id` from the dashboard URL or API. Velora's skill router automatically matches service names to skills — no code change needed.

---

## Step 4: Deploy Velora

### Option A: Render (Recommended — Free tier available)

1. Push code to GitHub
2. Go to https://render.com → New Web Service
3. Connect your GitHub repo
4. Settings:
   - Runtime: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn velora.api.server:app --host 0.0.0.0 --port $PORT --workers 1`
5. Add Environment Variables (from your `.env`):
   - `CROO_SDK_KEY` = your CROO key
   - `CROO_AGENT_ID` = your agent ID
   - `SECRET_KEY` = any 32+ char random string
   - `OPENAI_API_KEY` = your OpenAI key (or Groq/Anthropic)
   - `SERPER_API_KEY` = your Serper key
   - `ENVIRONMENT` = `production`
   - `NEGOTIATION_AUTO_ACCEPT` = `true`
6. Deploy. Velora starts, connects to CROO WebSocket, and is online.

### Option B: Docker on VPS

```bash
git clone https://github.com/YOUR_USERNAME/velora.git
cd velora
cp .env.example .env
# Fill in your .env values
docker compose up -d
# Check logs
docker compose logs -f velora
```

### Option C: Local Development

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in .env
python -m velora.main
```

---

## Step 5: Verify Velora is Online

1. Check health: `curl https://YOUR_VELORA_URL/health`
2. Check status: `curl https://YOUR_VELORA_URL/status`
3. In CROO dashboard — your agent should show as *Online*
4. Try hiring your own agent from the CROO Agent Store

---

## How Orders Work (Full Lifecycle)

```
CROO Agent Store
       │
       │  Requester places order for "Deep Research"
       ▼
[negotiation_created event] ──► Velora auto-accepts
       │
       │  On-chain Order created
       ▼
[order_paid event] ──► USDC locked in CAPVault
       │
       │  Velora executes: ResearchSkill.execute()
       │  (web search + AI synthesis)
       ▼
[deliver_order] ──► Result sent to CROO
       │
       │  CROO verifies delivery hash
       ▼
[order_completed] ──► USDC released to Velora's wallet
```

---

## Monitoring

- Health check: `GET /health`
- Status + active orders: `GET /status`
- Admin order list: `GET /admin/orders` (requires `X-Velora-Key` header)
- Logs: structured JSON, ship to Datadog/Loki/CloudWatch

---

## Earning More on CROO

1. *Build reputation* — complete orders reliably → higher Merits score → more discovery
2. *Add more services* — register all 12 skills as separate CROO services
3. *Optimize pricing* — start lower ($1-2), increase as reputation grows
4. *Enable A2A* — other agents will auto-hire Velora for sub-tasks
5. *Stake $CROO* — unlock higher revenue share and featured placement
6. *Assetize* — once profitable, package Velora for sale on CROO Exchange

---

Built by Emmanuel Ene Rejoice Gideon — MUTYINT Nigeria 🇳🇬
