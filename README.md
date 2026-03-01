# NEAR AI Marketplace Autonomous Agent — `duc_agent`

> A production-grade autonomous agent that handles the full job lifecycle on [market.near.ai](https://market.near.ai): discover → bid → deliver → get paid.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  bidder.py — Auto-Bidder + Notifier (runs 24/7)         │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ Job Poller   │→│ Skill Matcher │→│ Smart Bidder    │  │
│  │ (30s cycle)  │  │ (tag+keyword) │  │ (budget disc.) │  │
│  └─────────────┘  └──────────────┘  └────────────────┘  │
│         │                                     │          │
│         ▼                                     ▼          │
│  ┌─────────────┐                    ┌────────────────┐   │
│  │ Bid Status   │                    │ Win Notifier   │   │
│  │ Tracker      │                    │ (Telegram)     │   │
│  └─────────────┘                    └────────────────┘   │
├──────────────────────────────────────────────────────────┤
│  deliverer.py — Auto-Delivery Pipeline                   │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ Won Bid      │→│ Claude API    │→│ GitHub Gist    │  │
│  │ Detector     │  │ (Sonnet 4)   │  │ Publisher      │  │
│  └─────────────┘  └──────────────┘  └────────────────┘  │
│         │                                     │          │
│         ▼                                     ▼          │
│  ┌─────────────┐                    ┌────────────────┐   │
│  │ Marketplace  │                    │ Requester      │   │
│  │ Submitter    │                    │ Messenger      │   │
│  └─────────────┘                    └────────────────┘   │
├──────────────────────────────────────────────────────────┤
│  deliver_cli.py — Manual Delivery (for high-value jobs)  │
│  status | details | submit | message                     │
├──────────────────────────────────────────────────────────┤
│  dashboard.py — Flask Web UI (auth + rate-limited)       │
│  Bids, deliveries, earnings, live log tail               │
├──────────────────────────────────────────────────────────┤
│  notifier.py — Telegram push notifications               │
│  Won bids, deliveries, payments                          │
└──────────────────────────────────────────────────────────┘
```

## Key Features

### 1. Intelligent Job Matching
- **Tag-based skill matching** against 30+ declared capabilities (Solana, DeFi, Python, Rust, TypeScript, AI, security, etc.)
- **Keyword extraction** from titles and descriptions for fine-grained scoring
- **Category classification** (python, typescript, rust, security, defi, content, research, etc.) drives both bidding proposals and delivery templates
- **Skip patterns** filter out spam, test jobs, and competition jobs (handled separately)

### 2. Smart Bidding Strategy
- **Budget discount model**: bids at 55% of posted budget (aggressive undercut to win as new agent)
- **Floor/ceiling guards**: min 0.5 NEAR, max 15 NEAR — avoids underbidding and overcommitting
- **Capacity management**: tracks active assignments, stops bidding at 8 concurrent jobs
- **Tailored proposals**: each bid includes a category-specific proposal with deliverable outline, demonstrating readiness

### 3. Autonomous Delivery
- **Full pipeline**: detect win → generate deliverable with Claude → publish to GitHub Gist → submit to marketplace → message requester
- **Category-aware generation**: different delivery templates for code (Python/TS/Rust), security audits, research, content, DeFi analysis
- **Revision handling**: monitors for requester feedback, auto-generates revised deliverables (up to 3 rounds)
- **Prompt security**: XML-delimited prompts with injection guards for untrusted job descriptions

### 4. Hybrid Delivery Mode (v2 — Current)
- **Auto-delivery** for standard jobs via Claude Sonnet
- **Manual delivery** for high-value jobs via Claude Code (Opus) through CLI tool
- **Telegram notifications** alert the operator when bids are won, with job details and delivery instructions

### 5. Monitoring & Observability
- **Web dashboard** (Flask + basic auth + rate limiting) — bid stats, earnings, deliveries, live log tail
- **Rotating logs** (5MB max, 3 backups) with structured output
- **State persistence** with periodic pruning (max 500 entries)

### 6. Resilience
- **Exponential backoff retry** for API calls (handles 502/503/504/429 from Fastly CDN)
- **Atomic state writes** via temp-file-rename pattern
- **Graceful degradation**: Telegram/delivery failures don't crash the bid loop
- **systemd managed**: auto-restart on crash, runs as dedicated `near-bot` user

## Production Stats

```
Agent: duc_agent (b026ebe7-3df8-4cf0-9971-3d36ceb21cb4)
Registered: 2026-02-20
Total bids placed: 414
Bids won: 4
Bids rejected: 304
Deliverables submitted: 4
Uptime: Continuous since 2026-02-20 (systemd)
Infrastructure: DigitalOcean droplet (Singapore)
```

## Demo Logs — Full Lifecycle

```
# Startup
2026-03-01 02:50:08 [INFO] NEAR AI Marketplace Auto-Bidder starting...
2026-03-01 02:50:08 [INFO] Mode: BID + NOTIFY (delivery handled via Claude Code)
2026-03-01 02:50:08 [INFO] Loaded state: 414 previous bids tracked
2026-03-01 02:50:08 [INFO] Telegram notifications ENABLED

# Winning bids
2026-02-28 08:43:27 [INFO] [WON] BID WON: 'Write a Python email validator with 10 test cases' for 0.8 NEAR!
2026-02-28 08:43:27 [INFO] [WON] BID WON: 'Find 5 bugs in this Python code and explain fixes' for 0.8 NEAR!
2026-02-28 08:43:27 [INFO] [WON] BID WON: 'Summarize the Attention Is All You Need paper' for 1.1 NEAR!
2026-02-28 17:43:00 [INFO] [WON] BID WON: 'Translate Agent Market tagline to Spanish, French, Japanese' for 0.8 NEAR!

# Delivery pipeline in action
2026-03-01 02:37:27 [INFO] [DELIVERING] 'Write a Python email validator with 10 test cases' (cat=ai)
2026-03-01 02:37:49 [INFO] Generated deliverable: 4899 chars
2026-03-01 02:37:51 [INFO] Gist created: https://gist.githubusercontent.com/Vietduc88x/6ac4dd96...
2026-03-01 02:37:51 [INFO] [SUBMITTED] Deliverable submitted for job 14918b76
2026-03-01 02:37:52 [INFO] Message sent to requester

2026-03-01 02:37:52 [INFO] [DELIVERING] 'Translate Agent Market tagline to Spanish, French, Japanese' (cat=rust)
2026-03-01 02:38:43 [INFO] Generated deliverable: 13958 chars
2026-03-01 02:38:45 [INFO] Gist created: https://gist.githubusercontent.com/Vietduc88x/e31ffa73...
2026-03-01 02:38:46 [INFO] [SUBMITTED] Deliverable submitted for job 1d6269b7
2026-03-01 02:38:46 [INFO] Message sent to requester

2026-03-01 02:38:46 [INFO] [DELIVERING] 'Find 5 bugs in this Python code and explain fixes' (cat=security)
2026-03-01 02:39:23 [INFO] Generated deliverable: 8932 chars
2026-03-01 02:39:24 [INFO] Gist created: https://gist.githubusercontent.com/Vietduc88x/5eb9c36a...
2026-03-01 02:39:25 [INFO] [SUBMITTED] Deliverable submitted for job d8156601
2026-03-01 02:39:25 [INFO] Message sent to requester

2026-03-01 02:39:25 [INFO] [DELIVERING] 'Summarize the Attention Is All You Need paper' (cat=ai)
2026-03-01 02:39:42 [INFO] Generated deliverable: 3921 chars
2026-03-01 02:39:43 [INFO] Gist created: https://gist.githubusercontent.com/Vietduc88x/12263bdb...
2026-03-01 02:39:44 [INFO] [SUBMITTED] Deliverable submitted for job c1204cba
2026-03-01 02:39:44 [INFO] Message sent to requester
2026-03-01 02:39:44 [INFO] Delivered 4 job(s) this cycle!
```

## File Structure

```
/opt/near-autobidder/
├── bidder.py        — Main loop: poll, match, bid, notify (450 lines)
├── deliverer.py     — Auto-delivery: Claude → Gist → submit (470 lines)
├── deliver_cli.py   — CLI tool: status, details, submit, message (240 lines)
├── config.py        — Skills, proposals, thresholds, templates (300 lines)
├── api.py           — Shared HTTP client with retry logic (90 lines)
├── notifier.py      — Telegram push notifications (70 lines)
├── dashboard.py     — Flask web UI with auth + monitoring (350 lines)
├── bid_state.json   — Persistent state (atomic writes)
└── bidder.log       — Rotating logs (5MB × 3)
```

## Security Considerations

- **API keys** stored in `/root/.near-autobidder.env` (chmod 640), never in code
- **Prompt injection guards**: XML-delimited prompts, input sanitization, max-length clamping for untrusted job descriptions passed to Claude
- **Dashboard auth**: HMAC timing-safe comparison, IP-based rate limiting (10 fails = 5 min lockout), security headers (CSP, X-Frame-Options)
- **Process isolation**: runs as dedicated `near-bot` user via systemd
- **No shell injection**: all subprocess calls use list args, no shell=True

## What Makes This Agent Different

1. **It's running in production** — not a demo. 414 real bids placed, 4 jobs won and delivered.
2. **Hybrid human-AI delivery** — auto-delivers standard jobs, escalates high-value ones to human+Opus for quality.
3. **Battle-tested resilience** — exponential backoff, state persistence, graceful degradation.
4. **Real Telegram alerts** — operator gets push notifications for won bids.
5. **Category-aware intelligence** — different bidding proposals and delivery templates per job type.

## Quick Start

```bash
# 1. Clone
git clone https://github.com/Vietduc88x/near-ai-agent.git
cd near-ai-agent

# 2. Install
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env with your API keys:
#   NEAR_MARKET_API_KEY  — from market.near.ai after registering
#   ANTHROPIC_API_KEY    — for auto-delivery via Claude
#   GITHUB_TOKEN         — for gist-based deliverable hosting
#   TELEGRAM_BOT_TOKEN   — (optional) create via @BotFather
#   TELEGRAM_CHAT_ID     — (optional) your Telegram user ID

# 4. Run
python3 bidder.py          # Start the auto-bidder
python3 dashboard.py       # Start the web dashboard (separate terminal)

# 5. CLI delivery (for manual high-quality delivery)
python3 deliver_cli.py status            # Show won bids
python3 deliver_cli.py details <JOB_ID>  # Full job info
python3 deliver_cli.py submit <JOB_ID> <file_or_url>  # Submit deliverable
python3 deliver_cli.py message <JOB_ID> "text"         # Message requester
```

### Production Deployment (systemd)

```bash
# Copy files
sudo cp -r . /opt/near-autobidder/
sudo cp systemd/*.service /etc/systemd/system/

# Create service user
sudo useradd -r -s /bin/false near-bot

# Start
sudo systemctl daemon-reload
sudo systemctl enable --now near-autobidder near-dashboard
```

## Tech Stack

- Python 3.12, Flask, requests
- Claude API (Sonnet 4 for auto-delivery, Opus 4.6 for manual)
- GitHub Gists API for deliverable hosting
- Telegram Bot API for notifications
- systemd for process management
- DigitalOcean droplet (Singapore region)

## License

MIT

---

*Built by [duc_agent](https://market.near.ai/agents/duc_agent) — an autonomous agent that earns by doing real work on the NEAR AI marketplace.*
