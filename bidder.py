"""NEAR AI Marketplace Auto-Bidder.

Polls for new open jobs, matches against our skills, and places bids automatically.
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import json
import os
import tempfile
import time
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import (
    AGENT_ID,
    POLL_INTERVAL,
    DEFAULT_ETA_SECONDS,
    MAX_BID_NEAR,
    MIN_BID_NEAR,
    BUDGET_DISCOUNT,
    OUR_SKILLS,
    SKILL_KEYWORDS,
    PROPOSALS,
    SKIP_TITLE_PATTERNS,
    MAX_ACTIVE_ASSIGNMENTS,
)
from api import api_get, api_post, get_my_bids

# --- H-4: Log rotation with RotatingFileHandler ---
LOG_FILE = Path(__file__).parent / "bidder.log"
_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
_stream_handler = logging.StreamHandler()
_stream_handler.setFormatter(_formatter)
_file_handler = RotatingFileHandler(
    LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
_file_handler.setFormatter(_formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[_stream_handler, _file_handler],
)
log = logging.getLogger("autobidder")

# State file to track bids we've already placed
STATE_FILE = Path(__file__).parent / "bid_state.json"

# H-4: Max entries to keep in state (prune oldest)
_MAX_STATE_ENTRIES = 500


def load_state() -> dict:
    """Load bid tracking state from disk."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"bids_placed": {}, "jobs_skipped": [], "total_bids": 0, "total_earned": 0.0}


def save_state(state: dict):
    """H-3: Atomic save — write to temp then rename to prevent corruption."""
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=STATE_FILE.parent, suffix=".tmp", prefix="bid_state_"
        )
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2, default=str)
        os.replace(tmp_path, STATE_FILE)
    except Exception:
        # Clean up temp file if rename failed
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def prune_state(state: dict):
    """H-4: Prune old entries from state to prevent unbounded growth."""
    bids = state.get("bids_placed", {})
    if len(bids) <= _MAX_STATE_ENTRIES:
        return

    # Sort by placed_at, keep newest _MAX_STATE_ENTRIES
    sorted_entries = sorted(
        bids.items(),
        key=lambda x: x[1].get("placed_at", ""),
        reverse=True,
    )
    state["bids_placed"] = dict(sorted_entries[:_MAX_STATE_ENTRIES])
    log.info(f"Pruned state: kept {_MAX_STATE_ENTRIES} of {len(bids)} entries")




def get_open_jobs() -> list[dict]:
    """Fetch all open standard jobs, sorted by newest first."""
    jobs = api_get("/v1/jobs", {
        "status": "open",
        "sort": "created_at",
        "order": "desc",
        "limit": 100,
    })
    return jobs or []


def get_active_assignment_count() -> int:
    """Count how many in-progress assignments we have."""
    bids = get_my_bids()
    active = sum(1 for b in bids if b.get("status") == "accepted")
    return active


def _safe_float(val, default: float = 0.0) -> float:
    """M-2: Safely parse a float from untrusted input."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def should_skip_job(job: dict) -> tuple[bool, str]:
    """Check if we should skip this job."""
    title = (job.get("title") or "").lower()

    # Skip test/spam jobs
    for pattern in SKIP_TITLE_PATTERNS:
        if pattern.lower() in title:
            return True, f"spam/test pattern: {pattern}"

    # Skip competition jobs (we bid on those manually)
    if job.get("job_type") == "competition":
        return True, "competition job (manual)"

    # Skip jobs with no budget (hard to price)
    if not job.get("budget_amount"):
        return True, "no budget specified"

    budget = _safe_float(job.get("budget_amount", 0))

    # Skip very low budget jobs (not worth the effort)
    if budget < MIN_BID_NEAR:
        return True, f"budget too low: {budget} NEAR"

    # Skip very high budget jobs (likely complex, need manual review)
    if budget > MAX_BID_NEAR * 2:
        return True, f"budget too high: {budget} NEAR (manual review needed)"

    return False, ""


def compute_skill_match(job: dict) -> tuple[float, str]:
    """Compute skill match score (0-1) and best matching category.

    Returns (score, best_category).
    """
    tags = set(t.lower() for t in (job.get("tags") or []))
    title = (job.get("title") or "").lower()
    desc = (job.get("description") or "").lower()[:500]
    text = f"{title} {desc} {' '.join(tags)}"

    # Direct tag matches
    tag_matches = tags & OUR_SKILLS
    tag_score = len(tag_matches) / max(len(tags), 1) if tags else 0

    # Keyword matches
    category_scores = {}
    for category, keywords in SKILL_KEYWORDS.items():
        matches = sum(1 for kw in keywords if kw in text)
        if matches > 0:
            category_scores[category] = matches / len(keywords)

    # Best category
    best_category = "default"
    best_cat_score = 0
    for cat, score in category_scores.items():
        if score > best_cat_score:
            best_cat_score = score
            best_category = cat

    # Combined score
    keyword_score = min(best_cat_score, 1.0)
    combined = (tag_score * 0.4) + (keyword_score * 0.6)

    # Boost for NEAR-related jobs (core marketplace demand)
    if "near" in text:
        combined = min(combined + 0.2, 1.0)

    return combined, best_category


def compute_bid_amount(job: dict) -> float:
    """Compute optimal bid amount based on budget and competition."""
    budget = _safe_float(job.get("budget_amount", 0))

    # Bid at discount to budget (undercut)
    bid = budget * BUDGET_DISCOUNT

    # Clamp
    bid = max(MIN_BID_NEAR, min(bid, MAX_BID_NEAR))

    # Round to 1 decimal
    return round(bid, 1)


def _build_deliverable_outline(job: dict, category: str) -> str:
    """Generate a concrete deliverable outline to show we're ready to start."""
    title = (job.get("title") or "").strip()
    desc = (job.get("description") or "")[:300].strip()

    # Category-specific outline structures
    outlines = {
        "python": f"Deliverable plan:\n1. Core module with type hints + docstrings\n2. requirements.txt + setup instructions\n3. Unit tests with pytest\n4. README with usage examples",
        "typescript": f"Deliverable plan:\n1. TypeScript source with full typing\n2. package.json + tsconfig\n3. Jest/Vitest tests\n4. README with setup + examples",
        "rust": f"Deliverable plan:\n1. Cargo project with proper error handling\n2. Integration tests\n3. README with build + run instructions",
        "security": f"Deliverable plan:\n1. Executive summary with risk matrix\n2. Detailed findings (Critical/High/Medium/Low)\n3. Code snippets showing vulnerable patterns\n4. Prioritized remediation roadmap",
        "defi": f"Deliverable plan:\n1. Working integration code with error handling\n2. Protocol interaction logic + edge cases\n3. Risk analysis for financial operations\n4. Test suite for critical paths",
        "ai": f"Deliverable plan:\n1. Complete implementation with prompt engineering\n2. API integration with retry/error handling\n3. Configuration + environment setup\n4. Usage examples with expected outputs",
        "bot": f"Deliverable plan:\n1. Bot source with command handlers\n2. Config/env setup + deployment script\n3. Error recovery + logging\n4. README with features list",
        "near": f"Deliverable plan:\n1. NEAR SDK integration code\n2. RPC interaction + account handling\n3. Deployment scripts + testnet config\n4. Documentation with examples",
        "data": f"Deliverable plan:\n1. Data collection/processing scripts\n2. Structured dataset with methodology\n3. Analysis results + key findings\n4. Actionable recommendations",
        "content": f"Deliverable plan:\n1. Well-structured article with headers\n2. Researched content with cited sources\n3. SEO-friendly formatting\n4. Ready-to-publish quality",
        "blockchain": f"Deliverable plan:\n1. Smart contract / integration code\n2. Deployment + interaction scripts\n3. Security considerations\n4. Full documentation",
    }
    return outlines.get(category, outlines.get("content",
        "Deliverable plan:\n1. Complete implementation\n2. Documentation + examples\n3. Tests\n4. README"))


def generate_proposal(job: dict, category: str) -> str:
    """Generate a tailored proposal with deliverable outline to show readiness."""
    base = PROPOSALS.get(category, PROPOSALS["default"])

    title = job.get("title", "")
    tags = job.get("tags", [])

    # Direct, confident opener that addresses the job
    opener = f"I can deliver '{title}' within 12 hours. "

    # Add tag-specific credibility
    lower_tags = [t.lower() for t in tags]
    if "mcp" in lower_tags:
        opener += "Built production MCP servers for Claude. "
    if "openclaw" in lower_tags:
        opener += "Familiar with OpenClaw skill framework. "
    if any(t in ["near", "ref-finance"] for t in lower_tags):
        opener += "Active NEAR ecosystem builder. "

    # Add deliverable outline — shows we've already planned the work
    outline = _build_deliverable_outline(job, category)

    proposal = opener + base + "\n\n" + outline

    # Trim to reasonable length (marketplace may cap proposal length)
    if len(proposal) > 1200:
        proposal = proposal[:1197] + "..."

    return proposal


def place_bid(job: dict, state: dict) -> bool:
    """Place a bid on a job. Returns True if successful."""
    job_id = job["job_id"]

    # Compute bid details
    match_score, category = compute_skill_match(job)
    bid_amount = compute_bid_amount(job)
    proposal = generate_proposal(job, category)

    log.info(
        f"  Bidding on '{job.get('title', '')[:60]}' | "
        f"{bid_amount} NEAR | match={match_score:.2f} | cat={category}"
    )

    result = api_post(f"/v1/jobs/{job_id}/bids", {
        "amount": str(bid_amount),
        "eta_seconds": DEFAULT_ETA_SECONDS,
        "proposal": proposal,
    })

    if result and "bid_id" in result:
        log.info(f"  [OK] Bid placed: {result['bid_id']}")
        state["bids_placed"][job_id] = {
            "bid_id": result["bid_id"],
            "amount": bid_amount,
            "title": job.get("title", ""),
            "category": category,
            "match_score": match_score,
            "placed_at": datetime.now(timezone.utc).isoformat(),
        }
        state["total_bids"] += 1
        save_state(state)
        return True
    elif result and result.get("error") == "duplicate":
        # 409: we already bid on this job — record it so we don't retry
        log.info(f"  [DUP] Already bid on '{job.get('title', '')[:50]}' — recording to skip")
        state["bids_placed"][job_id] = {
            "bid_id": "duplicate",
            "amount": bid_amount,
            "title": job.get("title", ""),
            "category": category,
            "match_score": match_score,
            "status": "duplicate",
            "placed_at": datetime.now(timezone.utc).isoformat(),
        }
        save_state(state)
        return False
    else:
        log.warning(f"  [FAIL] Bid failed on {job_id}")
        return False


def check_bid_statuses(state: dict):
    """Check status of our existing bids and log any changes."""
    bids = get_my_bids()
    if not bids:
        return

    for bid in bids:
        bid_id = bid["bid_id"]
        status = bid["status"]
        job_id = bid["job_id"]

        if status == "accepted":
            if job_id in state["bids_placed"]:
                prev = state["bids_placed"][job_id]
                if prev.get("status") not in ("won", "delivered", "completed"):
                    log.info(f"  [WON] BID WON: '{prev.get('title', job_id)}' for {bid['amount']} NEAR!")
                    prev["status"] = "won"
                    save_state(state)
                    # Send Telegram notification
                    try:
                        from notifier import notify_bid_won
                        notify_bid_won(
                            title=prev.get("title", job_id),
                            amount=str(bid.get("amount", "?")),
                            job_id=job_id,
                            tags=prev.get("tags", []),
                        )
                    except Exception as e:
                        log.warning(f"Notification failed: {e}")

        elif status == "rejected":
            if job_id in state["bids_placed"]:
                prev = state["bids_placed"][job_id]
                if prev.get("status") != "rejected":
                    log.info(f"  [REJECTED] Bid rejected: '{prev.get('title', job_id)}'")
                    prev["status"] = "rejected"
                    save_state(state)


def run_cycle(state: dict) -> int:
    """Run one polling cycle. Returns number of new bids placed."""
    # Check how many active assignments we have
    active = get_active_assignment_count()
    if active >= MAX_ACTIVE_ASSIGNMENTS:
        log.info(f"At capacity ({active}/{MAX_ACTIVE_ASSIGNMENTS} active). Skipping bidding.")
        return 0

    # Check existing bid statuses
    check_bid_statuses(state)

    # Fetch open jobs
    jobs = get_open_jobs()
    if not jobs:
        log.info("No open jobs found.")
        return 0

    new_bids = 0
    already_bid = set(state["bids_placed"].keys())

    for job in jobs:
        job_id = job["job_id"]

        # Skip if we already bid
        if job_id in already_bid:
            continue

        # Skip if in skip list
        if job_id in state.get("jobs_skipped", []):
            continue

        # Check if we should skip
        skip, reason = should_skip_job(job)
        if skip:
            log.debug(f"  Skipping '{job.get('title', '')[:40]}': {reason}")
            continue

        # Check skill match
        match_score, category = compute_skill_match(job)
        if match_score < 0.10:
            log.debug(f"  Low match ({match_score:.2f}): '{job.get('title', '')[:40]}'")
            continue

        # Place bid
        success = place_bid(job, state)
        if success:
            new_bids += 1

        # Small delay between bids to avoid rate limiting
        time.sleep(2)

    return new_bids


def main():
    """Main loop: poll for jobs, bid, and notify on wins."""
    log.info("=" * 60)
    log.info("NEAR AI Marketplace Auto-Bidder starting...")
    log.info("Mode: BID + NOTIFY (delivery handled via Claude Code)")
    log.info(f"Agent: {AGENT_ID}")
    log.info(f"Poll interval: {POLL_INTERVAL}s")
    log.info(f"Max bid: {MAX_BID_NEAR} NEAR | Budget discount: {BUDGET_DISCOUNT}")
    log.info(f"Max active assignments: {MAX_ACTIVE_ASSIGNMENTS}")
    log.info("=" * 60)

    state = load_state()
    log.info(f"Loaded state: {state['total_bids']} previous bids tracked")

    # Check Telegram config
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if tg_token and tg_chat:
        log.info("Telegram notifications ENABLED")
    else:
        log.warning("Telegram not configured — won bids logged only (no push alerts)")

    cycle = 0

    while True:
        cycle += 1
        log.info(f"\n--- Cycle {cycle} | {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')} ---")

        try:
            new_bids = run_cycle(state)
            if new_bids > 0:
                log.info(f"Placed {new_bids} new bid(s) this cycle")
            else:
                log.info("No new bids this cycle")
        except Exception as e:
            log.error(f"Bid cycle error: {e}", exc_info=True)

        # H-4: Periodic state pruning
        if cycle % 50 == 0:
            prune_state(state)
            save_state(state)

        won_count = sum(1 for b in state.get("bids_placed", {}).values() if b.get("status") == "won")
        log.info(f"Total bids: {state['total_bids']} | Won pending: {won_count} | Earned: {state.get('total_earned', 0):.1f} NEAR")
        log.info(f"Sleeping {POLL_INTERVAL}s...")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
