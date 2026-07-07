"""todo_write tool schema (Claude Code TodoWrite-style discipline)."""

TODO_WRITE_TOOL = {
    "name": "todo_write",
    "description": (
        "Create and manage a structured task list for the current session. "
        "This is the single source of truth for what you are doing — keep it aligned with real progress.\n\n"
        "## When to use\n"
        "- Multi-step work (3+ distinct steps) or non-trivial implementation\n"
        "- User gives multiple tasks, a numbered list, or a plan to follow\n"
        "- Immediately after new instructions — capture requirements as todos before other tools\n"
        "- Before starting a step: set that item to in_progress; when finished: mark completed right away\n\n"
        "## When NOT to use\n"
        "- Single trivial action (one read, one answer, one obvious command)\n"
        "- Purely conversational or informational requests\n"
        "- Work already fully tracked and unchanged\n\n"
        "## Rules (strict)\n"
        "- Pass the **complete** todos array every call — the harness replaces the entire list\n"
        "- **Exactly one** todo may be `in_progress` at a time\n"
        "- Mark `in_progress` **before** starting work on that item\n"
        "- Mark `completed` **immediately** when done — do not batch-update at the end\n"
        "- Never mark `completed` if tests fail, work is partial, or blockers remain\n"
        "- `content`: imperative, for you (e.g. \"Run tests\", \"Fix loop counter\")\n"
        "- `activeForm`: present continuous, for the user (e.g. \"Running tests…\", \"Fixing loop counter…\")\n\n"
        "## Good pattern\n"
        "1. User asks for a feature → todo_write with all steps pending, first step in_progress\n"
        "2. Finish step → todo_write: step1 completed, step2 in_progress\n"
        "3. All done → every item completed before ending\n\n"
        "## Bad pattern\n"
        "- All items stay pending while you work\n"
        "- Multiple in_progress items\n"
        "- Calling todo_write once at start and never again\n"
        "- Marking everything completed without doing the work"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "description": "Complete session task list (replaces previous list)",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "Imperative task description for the agent",
                        },
                        "activeForm": {
                            "type": "string",
                            "description": "Present continuous label shown while in progress",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed"],
                        },
                    },
                    "required": ["content", "activeForm", "status"],
                },
            }
        },
        "required": ["todos"],
    },
}
