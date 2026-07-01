"""Runtime paths, LLM client, and harness constants."""

from __future__ import annotations

import os
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
WORKDIR = Path.cwd()

load_dotenv(PACKAGE_ROOT / ".env")
load_dotenv(override=True)
if os.getenv("ANTHROPIC_BASE_URL"):
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

SKILLS_DIR = PACKAGE_ROOT / "skills"
CONFIG_DIR = PACKAGE_ROOT / "config"
MCP_CONFIG_PATH = CONFIG_DIR / "mcp.json"

TRANSCRIPT_DIR = WORKDIR / ".transcripts"
TOOL_RESULTS_DIR = WORKDIR / ".task_outputs" / "tool-results"
TASKS_DIR = WORKDIR / ".tasks"
WORKTREES_DIR = WORKDIR / ".worktrees"
MAILBOX_DIR = WORKDIR / ".mailboxes"
MEMORY_DIR = WORKDIR / ".memory"
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"
DURABLE_CRON_PATH = WORKDIR / ".scheduled_tasks.json"

for path in (TASKS_DIR, WORKTREES_DIR, MAILBOX_DIR):
    path.mkdir(exist_ok=True)

client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
MODEL = os.environ["MODEL_ID"]
PRIMARY_MODEL = MODEL
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL_ID")

DEFAULT_MAX_TOKENS = 8000
ESCALATED_MAX_TOKENS = 16000
MAX_RETRIES = 3
MAX_CONSECUTIVE_529 = 2
MAX_RECOVERY_RETRIES = 2
BASE_DELAY_MS = 500
CONTEXT_LIMIT = 50000
KEEP_RECENT_TOOL_RESULTS = 3
PERSIST_THRESHOLD = 30000
CONTINUATION_PROMPT = (
    "Continue from the previous response. Do not repeat completed work."
)
CLI_PROMPT = "\033[36mharness >> \033[0m"

IDLE_POLL_INTERVAL = 5
IDLE_TIMEOUT = 60
