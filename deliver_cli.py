#!/usr/bin/env python3
"""CLI tool for checking and delivering won NEAR AI marketplace jobs.

Usage:
  python3 deliver_cli.py status          — Show won bids pending delivery
  python3 deliver_cli.py details <JOB>   — Show full job details
  python3 deliver_cli.py submit <JOB> <GIST_URL>  — Submit a deliverable
  python3 deliver_cli.py message <JOB> <TEXT>      — Message the requester
"""

import hashlib
import json
import os
import sys
from pathlib import Path

import requests

# Auto-load env file if not already set
ENV_FILE = Path("/root/.near-autobidder.env")
if ENV_FILE.exists() and not os.environ.get("NEAR_MARKET_API_KEY"):
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

API_BASE = "https://market.near.ai"
API_KEY = os.environ.get("NEAR_MARKET_API_KEY", "")
AGENT_ID = os.environ.get("NEAR_AGENT_ID", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def get_my_bids():
    r = requests.get(f"{API_BASE}/v1/agents/me/bids", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def get_job(job_id):
    r = requests.get(f"{API_BASE}/v1/jobs/{job_id}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def get_assignment_id(job):
    for a in job.get("my_assignments") or []:
        if a.get("status") in ("in_progress", "submitted"):
            return a.get("assignment_id")
    return None


def create_gist(content, title, filename=None):
    if not filename:
        safe = "".join(c if c.isalnum() or c in "-_ " else "" for c in title)
        filename = f"{safe.strip().replace(' ', '-')[:60]}.md"

    r = requests.post(
        "https://api.github.com/gists",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        },
        json={
            "description": f"NEAR AI Deliverable: {title}",
            "public": False,
            "files": {filename: {"content": content}},
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return data["files"][filename]["raw_url"]


def submit_deliverable(job_id, gist_url, content):
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    r = requests.post(
        f"{API_BASE}/v1/jobs/{job_id}/submit",
        headers=HEADERS,
        json={
            "deliverable_url": gist_url,
            "deliverable_hash": f"sha256:{content_hash}",
        },
        timeout=30,
    )
    r.raise_for_status()
    return True


def send_message(assignment_id, body):
    r = requests.post(
        f"{API_BASE}/v1/assignments/{assignment_id}/messages",
        headers=HEADERS,
        json={"body": body},
        timeout=30,
    )
    r.raise_for_status()
    return True


def get_messages(assignment_id):
    r = requests.get(
        f"{API_BASE}/v1/assignments/{assignment_id}/messages",
        headers=HEADERS,
        params={"limit": 10},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def cmd_status():
    """Show all won/in_progress jobs that need delivery."""
    bids = get_my_bids()
    won = [b for b in bids if b.get("status") == "accepted"]
    if not won:
        print("No won bids pending delivery.")
        return

    print(f"\n{'='*70}")
    print(f"  WON BIDS AWAITING DELIVERY ({len(won)})")
    print(f"{'='*70}\n")

    for b in won:
        job = get_job(b["job_id"])
        title = job.get("title", "?")[:60]
        budget = job.get("budget_amount", "?")
        tags = ", ".join(job.get("tags") or [])
        status = job.get("status", "?")
        has_deliverable = bool(job.get("deliverable"))
        print(f"  Job: {b['job_id']}")
        print(f"  Title: {title}")
        print(f"  Budget: {budget} NEAR | Bid: {b.get('amount', '?')} NEAR")
        print(f"  Tags: {tags}")
        print(f"  Status: {status} | Delivered: {'yes' if has_deliverable else 'NO'}")
        print(f"  {'-'*60}")


def cmd_details(job_id):
    """Show full job details including description."""
    job = get_job(job_id)
    print(f"\nTitle: {job.get('title')}")
    print(f"Budget: {job.get('budget_amount')} {job.get('budget_token')}")
    print(f"Type: {job.get('job_type')} | Status: {job.get('status')}")
    print(f"Tags: {', '.join(job.get('tags') or [])}")
    print(f"Bid count: {job.get('bid_count')}")
    print(f"Created: {job.get('created_at')}")
    print(f"Expires: {job.get('expires_at')}")
    print(f"\n{'='*60}")
    print("DESCRIPTION:")
    print(f"{'='*60}")
    print(job.get("description", "(empty)"))

    assignment_id = get_assignment_id(job)
    if assignment_id:
        print(f"\nAssignment ID: {assignment_id}")
        try:
            msgs = get_messages(assignment_id)
            if msgs:
                print(f"\n{'='*60}")
                print("MESSAGES:")
                print(f"{'='*60}")
                for m in msgs:
                    sender = m.get("sender_role", "?")
                    print(f"  [{sender}] {m.get('body', '')[:200]}")
        except Exception:
            pass


def cmd_submit(job_id, gist_url_or_file):
    """Submit deliverable — accepts gist URL or local file path."""
    job = get_job(job_id)
    title = job.get("title", "deliverable")

    # If it's a file path, read content and create gist
    if not gist_url_or_file.startswith("http"):
        with open(gist_url_or_file, "r", encoding="utf-8") as f:
            content = f.read()
        print(f"Read {len(content)} chars from {gist_url_or_file}")
        print("Creating gist...")
        gist_url = create_gist(content, title)
        print(f"Gist: {gist_url}")
    else:
        gist_url = gist_url_or_file
        r = requests.get(gist_url, timeout=30)
        content = r.text

    print("Submitting...")
    submit_deliverable(job_id, gist_url, content)
    print(f"SUBMITTED to job {job_id[:12]}")

    assignment_id = get_assignment_id(job)
    if assignment_id:
        send_message(
            assignment_id,
            f"Deliverable submitted for '{title}'. "
            f"Available at: {gist_url}\n\n"
            f"Please review. Happy to iterate if changes are needed.",
        )
        print("Message sent to requester.")

    # Update state
    try:
        with open("/opt/near-autobidder/bid_state.json", "r") as f:
            state = json.load(f)
        if job_id in state.get("bids_placed", {}):
            state["bids_placed"][job_id]["status"] = "delivered"
            state["bids_placed"][job_id]["deliverable_url"] = gist_url
            with open("/opt/near-autobidder/bid_state.json", "w") as f:
                json.dump(state, f)
            print("State updated.")
    except Exception as e:
        print(f"Warning: state update failed: {e}")


def cmd_message(job_id, text):
    """Send a message to the requester."""
    job = get_job(job_id)
    assignment_id = get_assignment_id(job)
    if not assignment_id:
        print("No active assignment found for this job.")
        return
    send_message(assignment_id, text)
    print(f"Message sent on assignment {assignment_id[:12]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "status":
        cmd_status()
    elif cmd == "details" and len(sys.argv) >= 3:
        cmd_details(sys.argv[2])
    elif cmd == "submit" and len(sys.argv) >= 4:
        cmd_submit(sys.argv[2], sys.argv[3])
    elif cmd == "message" and len(sys.argv) >= 4:
        cmd_message(sys.argv[2], " ".join(sys.argv[3:]))
    else:
        print(__doc__)
        sys.exit(1)
