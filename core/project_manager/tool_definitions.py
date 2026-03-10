"""
Anthropic-style tool definitions for the ProjectManager agent loop.

The PM agent does **not** directly edit files or run shell commands.
Instead, it decomposes work, dispatches to engineers, and monitors
progress via structured tools.
"""
from __future__ import annotations

PM_TOOLS: list[dict] = [
    # ------------------------------------------------------------------
    # Requirement decomposition
    # ------------------------------------------------------------------
    {
        "name": "plan_create",
        "description": (
            "Create a structured execution plan from user requirements. "
            "Break the requirements into discrete tasks and assign them "
            "to repositories.  Returns the plan ID."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short plan title."},
                "tasks": {
                    "type": "array",
                    "description": "List of sub-tasks.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "repo": {"type": "string", "description": "Repository display name."},
                            "description": {"type": "string", "description": "What the engineer should do."},
                            "acceptance_criteria": {"type": "string", "description": "How to verify completion."},
                            "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "Indices of prerequisite tasks (0-based).",
                            },
                        },
                        "required": ["repo", "description"],
                    },
                },
            },
            "required": ["title", "tasks"],
        },
    },
    {
        "name": "plan_list",
        "description": "List all existing plans and their statuses.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "plan_get",
        "description": "Get full details of a plan by ID.",
        "input_schema": {
            "type": "object",
            "properties": {"plan_id": {"type": "string"}},
            "required": ["plan_id"],
        },
    },
    # ------------------------------------------------------------------
    # Engineer dispatch & monitoring
    # ------------------------------------------------------------------
    {
        "name": "dispatch_task",
        "description": (
            "Send a task description to an engineer agent for a specific "
            "repository.  The engineer will execute autonomously.  Returns "
            "a tracking ID."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository display name."},
                "prompt": {"type": "string", "description": "Instructions for the engineer."},
                "plan_id": {"type": "string", "description": "Optional plan ID to associate with."},
                "task_index": {"type": "integer", "description": "Task index within the plan (0-based)."},
            },
            "required": ["repo", "prompt"],
        },
    },
    {
        "name": "check_engineer",
        "description": (
            "Check the current status and recent events from an engineer "
            "agent.  Returns status, last messages, and tool activity."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository display name."},
            },
            "required": ["repo"],
        },
    },
    {
        "name": "list_engineers",
        "description": "List all running engineer agents and their current statuses.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "stop_engineer",
        "description": "Stop a running engineer agent for a repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository display name."},
            },
            "required": ["repo"],
        },
    },
    # ------------------------------------------------------------------
    # Synchronous wait (Promise-style)
    # ------------------------------------------------------------------
    {
        "name": "wait_for_engineer",
        "description": (
            "Block until a specific engineer finishes its current task and "
            "return its final response.  Like await on a Promise.  "
            "Use this AFTER dispatch_task to wait for the result instead of "
            "polling with check_engineer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository display name."},
                "timeout": {
                    "type": "integer",
                    "description": "Max seconds to wait (default 300).",
                },
            },
            "required": ["repo"],
        },
    },
    {
        "name": "wait_for_engineers",
        "description": (
            "Wait for multiple engineers to finish in parallel, like Promise.all.  "
            "Returns all results once every engineer is idle or the timeout expires."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repos": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of repository display names.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Max seconds to wait for ALL engineers (default 600).",
                },
            },
            "required": ["repos"],
        },
    },
    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------
    {
        "name": "verify_task",
        "description": (
            "Ask an engineer to verify whether a dispatched task has been "
            "completed correctly according to the acceptance criteria."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository display name."},
                "acceptance_criteria": {"type": "string", "description": "What to verify."},
                "plan_id": {"type": "string"},
                "task_index": {"type": "integer"},
            },
            "required": ["repo", "acceptance_criteria"],
        },
    },
    # ------------------------------------------------------------------
    # Cross-repo coordination
    # ------------------------------------------------------------------
    {
        "name": "broadcast_engineers",
        "description": "Send a message to all running engineer agents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message to broadcast."},
            },
            "required": ["message"],
        },
    },
    {
        "name": "query_engineer",
        "description": (
            "Send a question to a specific engineer and wait for its response. "
            "Useful for gathering status or asking for summaries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "question": {"type": "string"},
            },
            "required": ["repo", "question"],
        },
    },
    # ------------------------------------------------------------------
    # Internal planning / tracking
    # ------------------------------------------------------------------
    {
        "name": "TodoWrite",
        "description": "Update the project manager's internal task checklist.",
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                            },
                        },
                        "required": ["content", "status"],
                    },
                },
            },
            "required": ["items"],
        },
    },
    # ------------------------------------------------------------------
    # Compression
    # ------------------------------------------------------------------
    {
        "name": "compress",
        "description": "Manually compress conversation context.",
        "input_schema": {"type": "object", "properties": {}},
    },
    # ------------------------------------------------------------------
    # Summary & reporting
    # ------------------------------------------------------------------
    {
        "name": "progress_report",
        "description": (
            "Generate a structured progress report across all dispatched "
            "tasks and engineer agents."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]
