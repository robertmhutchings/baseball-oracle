"""Agent configuration: model selection, paths, API key loading.

Centralized so model swaps and credential loading happen in exactly one
place. Imported by main.py at startup.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Model selection. Default per phase3_architecture.md §4: Sonnet 4.6.
# Swap to "claude-opus-4-7" if we hit quality issues we can't fix in prompt.
MODEL = "claude-sonnet-4-6"

# DB query guardrails per phase3_architecture.md §2.3
SQL_STATEMENT_TIMEOUT_MS = 30_000  # 30 seconds
SQL_MAX_ROWS = 1_000               # cap returned rows; agent told if truncated

# Conversation budget — single-question guardrail. Stops a runaway loop
# from racking up cost. Each agent "turn" = one round-trip to Anthropic.
MAX_AGENT_TURNS = 20


def get_anthropic_api_key() -> str:
    """Read ANTHROPIC_API_KEY from environment. Raises with a clear message if missing."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Add it to "
            f"{PROJECT_ROOT / '.env'} (line: ANTHROPIC_API_KEY=sk-ant-...)."
        )
    return key
