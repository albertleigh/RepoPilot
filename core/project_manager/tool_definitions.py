"""
Tool definitions for the ProjectManager agent loop.

The PM agent operates at two levels:

1. **Coordination** – plan, dispatch, wait, verify, debate with engineers.
2. **Direct action** – repo-scoped bash / read / write / edit so the PM
   can inspect code, run tests, or make surgical fixes itself when
   delegating would be wasteful.

All repo-scoped tools accept a ``repo`` parameter that is resolved via
the :class:`RepoRegistry` at call time.
"""
from __future__ import annotations

PM_TOOLS: list[dict] = [
    # ==================================================================
    # Direct repo access – bash / file operations
    # ==================================================================
    {
        "name": "bash",
        "description": (
            "Run a shell command inside a repository's working directory. "
            "Use for running tests, inspecting git status, searching code, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repository display name.",
                },
                "command": {
                    "type": "string",
                    "description": "Shell command to run.",
                },
            },
            "required": ["repo", "command"],
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read a file from any registered repository. "
            "Use to understand code, review engineer output, or gather "
            "context before making decisions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository display name."},
                "path": {"type": "string", "description": "Relative path within the repo."},
                "limit": {
                    "type": "integer",
                    "description": "Max lines to read (omit for all).",
                },
            },
            "required": ["repo", "path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Write content to a file in a repository. "
            "Use for creating configuration, shared interfaces, or making "
            "direct fixes when delegating to an engineer is overkill."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository display name."},
                "path": {"type": "string", "description": "Relative path within the repo."},
                "content": {"type": "string", "description": "File content to write."},
            },
            "required": ["repo", "path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Replace exact text in a file within a repository. "
            "Use for surgical edits — updating imports, fixing constants, "
            "tweaking configuration."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository display name."},
                "path": {"type": "string", "description": "Relative path within the repo."},
                "old_text": {"type": "string", "description": "Exact text to find."},
                "new_text": {"type": "string", "description": "Replacement text."},
            },
            "required": ["repo", "path", "old_text", "new_text"],
        },
    },
    # ==================================================================
    # Requirement decomposition & planning
    # ==================================================================
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
                    "description": "Ordered list of sub-tasks.",
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
    # ==================================================================
    # Engineer dispatch & monitoring
    # ==================================================================
    {
        "name": "dispatch_task",
        "description": (
            "Send a task to an engineer agent for autonomous execution. "
            "Be specific: include file paths, test commands, and acceptance "
            "criteria.  Returns a tracking ID."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository display name."},
                "prompt": {"type": "string", "description": "Detailed instructions for the engineer."},
                "plan_id": {"type": "string", "description": "Optional plan ID to associate with."},
                "task_index": {"type": "integer", "description": "Task index within the plan (0-based)."},
            },
            "required": ["repo", "prompt"],
        },
    },
    {
        "name": "check_engineer",
        "description": (
            "Check an engineer's live status and recent events. "
            "Returns status, last messages, and tool activity."
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
    # ==================================================================
    # Synchronous wait (Promise-style)
    # ==================================================================
    {
        "name": "wait_for_engineer",
        "description": (
            "Block until an engineer finishes and return its final response. "
            "Like await on a Promise.  Use AFTER dispatch_task."
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
            "Wait for multiple engineers to finish in parallel (Promise.all). "
            "Returns all results once every engineer is idle or timeout expires."
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
    # ==================================================================
    # Debate / discussion with engineers
    # ==================================================================
    {
        "name": "discuss_with_engineer",
        "description": (
            "Send a message to an engineer and WAIT for its complete response. "
            "Use for back-and-forth debate, code review, design discussion, "
            "or challenging an engineer's approach.  Returns the engineer's "
            "full reply.  Prefer this over dispatch_task + wait_for_engineer "
            "when you need a conversational exchange."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository display name."},
                "message": {
                    "type": "string",
                    "description": (
                        "Message to the engineer — question, critique, "
                        "design proposal, or review feedback."
                    ),
                },
                "timeout": {
                    "type": "integer",
                    "description": "Max seconds to wait for reply (default 300).",
                },
            },
            "required": ["repo", "message"],
        },
    },
    # ==================================================================
    # Verification
    # ==================================================================
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
    # ==================================================================
    # Cross-repo coordination & context sharing
    # ==================================================================
    {
        "name": "broadcast_engineers",
        "description": "Send a message to ALL running engineer agents.",
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
            "Send a question to an engineer (fire-and-forget). "
            "Use check_engineer later to read the response.  "
            "Prefer discuss_with_engineer for synchronous Q&A."
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
    {
        "name": "share_context",
        "description": (
            "Read a file from one repo and relay its contents to an engineer "
            "in another repo.  Essential for keeping cross-repo interfaces, "
            "contracts, and shared types in sync."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "source_repo": {
                    "type": "string",
                    "description": "Repo to read from.",
                },
                "source_path": {
                    "type": "string",
                    "description": "Relative file path in source repo.",
                },
                "target_repo": {
                    "type": "string",
                    "description": "Repo whose engineer receives the content.",
                },
                "message": {
                    "type": "string",
                    "description": (
                        "Context note sent alongside the file content, "
                        "explaining why it matters."
                    ),
                },
            },
            "required": ["source_repo", "source_path", "target_repo", "message"],
        },
    },
    # ==================================================================
    # Background execution
    # ==================================================================
    {
        "name": "background_run",
        "description": (
            "Run a long-running command (tests, builds) in the background "
            "inside a specific repo.  Returns a task ID for later checking."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository display name."},
                "command": {"type": "string"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 120)."},
            },
            "required": ["repo", "command"],
        },
    },
    {
        "name": "check_background",
        "description": "Check status of background tasks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Specific task ID, or omit for all."},
            },
        },
    },
    # ==================================================================
    # Internal planning / tracking
    # ==================================================================
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
    # ==================================================================
    # Compression
    # ==================================================================
    {
        "name": "compress",
        "description": "Manually compress conversation context.",
        "input_schema": {"type": "object", "properties": {}},
    },
    # ==================================================================
    # Summary & reporting
    # ==================================================================
    {
        "name": "progress_report",
        "description": (
            "Generate a structured progress report across all plans, "
            "dispatched tasks, and engineer agents."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]
