# Hooks Directory

Hooks are scripts or commands that fire automatically at specific lifecycle
events in the orchestrator. Each hook is a JSON file in this directory.

Hook file format:
```json
{
  "event": "pre_tool | post_tool | session_start | session_end | pre_compact",
  "tool_filter": "optional — tool name to match, or omit for all tools",
  "command": "shell command to execute",
  "inject_output": false,
  "description": "what this hook does"
}
```

Events:
- pre_tool: fires after the model requests a tool call, before execution
- post_tool: fires after a tool call completes successfully
- session_start: fires when the orchestrator initializes
- session_end: fires when the session terminates
- pre_compact: fires before context compaction

Output injection is supported for pre_tool, post_tool, and pre_compact. Tool
hook output reaches the next model context with the tool result; pre_compact
output is added as a system message. An inject_output definition for
session_start or session_end is refused because those events have no receiver.
Structured tool results remain valid JSON when output is injected.

Hook commands run with a 10-second timeout. If a hook times out or fails,
the orchestrator logs the failure and continues — hooks never block the
main agentic loop.
