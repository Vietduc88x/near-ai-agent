"""Configuration for the NEAR AI marketplace auto-bidder."""

import os

API_BASE = "https://market.near.ai"
API_KEY = os.environ.get("NEAR_MARKET_API_KEY", "")
AGENT_ID = os.environ.get("NEAR_AGENT_ID", "")

# Polling interval (seconds) — fast polling to bid before competition piles up
POLL_INTERVAL = 30  # Check every 30s

# Bidding strategy — aggressive undercut to win as new agent
DEFAULT_ETA_SECONDS = 43200  # 12 hours (signals fast delivery)
MAX_BID_NEAR = 15.0          # Never bid above this
MIN_BID_NEAR = 0.5           # Never bid below this
BUDGET_DISCOUNT = 0.55       # Bid 55% of budget (aggressive undercut to win)

# Skills we can deliver on
OUR_SKILLS = {
    "solana", "defi", "trading", "typescript", "rust", "python",
    "javascript", "ai", "security", "blockchain", "web3", "bot",
    "mcp", "claude", "api", "npm", "pypi", "automation",
    "code-review", "data-analysis", "research", "content",
    "near", "smart-contract", "wallet", "dex", "nft",
    "docker", "devops", "github-action", "tool", "skill",
    "openclaw", "langchain", "fastapi", "nextjs", "express",
}

# Keywords in title/description that signal a match
SKILL_KEYWORDS = {
    "python": ["python", "pypi", "pip", "flask", "fastapi", "django"],
    "typescript": ["typescript", "npm", "node", "express", "nextjs", "react"],
    "rust": ["rust", "cargo", "wasm"],
    "solana": ["solana", "anchor", "spl", "jupiter"],
    "defi": ["defi", "dex", "swap", "liquidity", "amm", "trading"],
    "security": ["security", "audit", "vulnerability", "review"],
    "ai": ["ai", "llm", "claude", "openai", "langchain", "mcp", "agent"],
    "bot": ["bot", "telegram", "discord", "slack", "automation"],
    "near": ["near", "ref-finance", "aurora"],
    "blockchain": ["blockchain", "smart contract", "web3", "crypto"],
    "data": ["data", "analysis", "scraping", "research", "dataset"],
    "content": ["content", "writing", "blog", "documentation", "marketing"],
}

# Proposal templates per skill category
PROPOSALS = {
    "python": (
        "Experienced Python developer with production systems in DeFi, trading bots, "
        "and data pipelines. I will deliver a clean, well-tested Python solution with "
        "comprehensive error handling, type hints, and documentation. "
        "Track record of building PyPI packages and CLI tools. 24h delivery."
    ),
    "typescript": (
        "Full-stack TypeScript developer with deep experience in Node.js, React, and "
        "blockchain integrations. I will build a production-ready solution with proper "
        "typing, error handling, and tests. Experienced with npm package publishing "
        "and MCP server development. 24h delivery."
    ),
    "rust": (
        "Systems developer experienced in Rust and smart contract development. "
        "I will deliver safe, performant Rust code with proper error handling "
        "and comprehensive tests. Deep experience with blockchain SDKs. 24h delivery."
    ),
    "security": (
        "Security-focused developer with smart contract auditing experience across "
        "Solana and NEAR ecosystems. I will perform thorough code review covering "
        "access control, injection vectors, and cryptographic correctness. "
        "Deliverable: structured report with severity ratings and remediation steps. 24h delivery."
    ),
    "defi": (
        "DeFi developer specializing in DEX integrations and trading systems. "
        "Production experience building grid bots, copy trading, and MEV systems "
        "on Solana/Jupiter. Deep understanding of AMM mechanics, orderbook DEXs, "
        "and on-chain trading. 24h delivery."
    ),
    "ai": (
        "AI/ML developer experienced in building LLM-powered agents, MCP servers, "
        "and Claude integrations. I will deliver a production-ready solution with "
        "proper prompt engineering, error handling, and documentation. 24h delivery."
    ),
    "bot": (
        "Bot developer with production experience building Telegram, Discord, and "
        "Slack bots. I will deliver a reliable, well-structured bot with proper "
        "command handling, error recovery, and deployment configuration. 24h delivery."
    ),
    "near": (
        "Blockchain developer experienced with the NEAR ecosystem. I will build "
        "a robust solution leveraging NEAR SDK, RPC, and tooling. Familiar with "
        "NEAR account model, access keys, and smart contract patterns. 24h delivery."
    ),
    "data": (
        "Data engineer experienced with large-scale data processing using Polars, "
        "Pandas, and Python. I will deliver an efficient, well-tested data pipeline "
        "with proper error handling and documentation. 24h delivery."
    ),
    "content": (
        "Technical writer and researcher with deep knowledge of blockchain, DeFi, "
        "and AI agent ecosystems. I will deliver well-researched, engaging content "
        "with proper sourcing and technical accuracy. 24h delivery."
    ),
    "default": (
        "Full-stack developer with production experience across Python, TypeScript, "
        "Rust, and blockchain ecosystems (Solana, NEAR). I will deliver a clean, "
        "well-tested solution with comprehensive error handling and documentation. "
        "24h delivery."
    ),
}

# Jobs to skip (test/spam patterns)
SKIP_TITLE_PATTERNS = ["job1", "test1", "hello world", "simple arithmetic"]

# Max concurrent active assignments (don't overcommit)
MAX_ACTIVE_ASSIGNMENTS = 8

# Auth headers (reusable)
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

# ---------------------------------------------------------------------------
# Auto-Delivery Configuration
# ---------------------------------------------------------------------------

# Delivery check interval (seconds) - separate from bid polling
DELIVERY_CHECK_INTERVAL = 120  # Check every 2 minutes

# System prompt for Claude when generating deliverables
DELIVERY_SYSTEM_PROMPT = (
    "You are a professional freelance developer and technical writer completing jobs "
    "on the NEAR AI Agent Marketplace. You produce high-quality, production-ready "
    "deliverables. Your work should be thorough, well-structured, and immediately "
    "usable by the requester.\n\n"
    "Format your output in clean Markdown. For code deliverables, include:\n"
    "- Complete, runnable code with comments\n"
    "- A README section explaining setup and usage\n"
    "- Example usage/output\n\n"
    "For content deliverables, include:\n"
    "- Well-researched, accurate information\n"
    "- Proper structure with headers and sections\n"
    "- Sources or references where applicable\n\n"
    "For research deliverables, include:\n"
    "- Executive summary\n"
    "- Detailed findings organized by topic\n"
    "- Actionable recommendations\n\n"
    "Do NOT include meta-commentary about the task. Just produce the deliverable."
)

# Category-specific delivery instructions
DELIVERY_CATEGORIES = {
    "python": (
        "Deliver a complete Python solution. Include:\n"
        "- All source code files with docstrings and type hints\n"
        "- requirements.txt for dependencies\n"
        "- README with installation, usage, and example output\n"
        "- Basic tests or test examples"
    ),
    "typescript": (
        "Deliver a complete TypeScript/Node.js solution. Include:\n"
        "- All source files with proper typing\n"
        "- package.json with dependencies\n"
        "- README with setup, usage, and examples\n"
        "- tsconfig.json if needed"
    ),
    "rust": (
        "Deliver a complete Rust solution. Include:\n"
        "- All source files with proper error handling\n"
        "- Cargo.toml with dependencies\n"
        "- README with build and run instructions\n"
        "- Tests module"
    ),
    "security": (
        "Deliver a security review/audit report. Include:\n"
        "- Executive summary with risk level\n"
        "- Detailed findings (severity, description, impact, remediation)\n"
        "- Code snippets showing vulnerable patterns\n"
        "- Prioritized remediation roadmap"
    ),
    "defi": (
        "Deliver a DeFi-focused solution or analysis. Include:\n"
        "- Complete implementation code\n"
        "- Protocol/contract interaction details\n"
        "- Risk considerations and edge cases\n"
        "- Testing approach for financial logic"
    ),
    "ai": (
        "Deliver an AI/LLM solution. Include:\n"
        "- Complete implementation with proper prompt engineering\n"
        "- API integration code with error handling\n"
        "- Configuration for model parameters\n"
        "- Usage examples and expected outputs"
    ),
    "bot": (
        "Deliver a complete bot implementation. Include:\n"
        "- All bot source code with command handlers\n"
        "- Configuration/environment setup\n"
        "- Deployment instructions (systemd/docker)\n"
        "- README with features and usage"
    ),
    "near": (
        "Deliver a NEAR ecosystem solution. Include:\n"
        "- Complete implementation using NEAR SDK/tools\n"
        "- Account/key management details\n"
        "- RPC interaction code\n"
        "- README with deployment and testing steps"
    ),
    "data": (
        "Deliver a data analysis or research dataset. Include:\n"
        "- Complete methodology description\n"
        "- Data collection/processing scripts\n"
        "- Analysis results with visualizations described\n"
        "- Key findings and recommendations"
    ),
    "content": (
        "Deliver polished, publication-ready content. Include:\n"
        "- Well-structured article/post with headers\n"
        "- Engaging introduction and clear conclusion\n"
        "- Technical accuracy with sources cited\n"
        "- SEO-friendly formatting if applicable"
    ),
    "blockchain": (
        "Deliver a blockchain-focused solution. Include:\n"
        "- Smart contract or integration code\n"
        "- Deployment and interaction scripts\n"
        "- Testing approach and security considerations\n"
        "- README with full setup instructions"
    ),
    "default": (
        "Deliver a thorough, professional solution. Include:\n"
        "- Complete implementation or content\n"
        "- Clear documentation and usage instructions\n"
        "- Any relevant tests or examples\n"
        "- README or summary section"
    ),
}
