"""
spawning.py — Spawning Protocol for Sub-Framework Execution (Phase 9)

During analysis, a model may determine that spawning a sub-framework would
improve output quality. This module manages:
  - Spawning policy evaluation (permitted/restricted/prohibited per mode)
  - Four execution modes: Sequential Local, Parallel Cloud, Deferred, Refused
  - Handoff package format for structured result return
  - Cost accounting for cloud spawns

Spawning policy is defined in mode files and boot context. The policy
controls whether and how spawning is permitted.

Usage:
    from orchestrator.tools.spawning import SpawnManager
    manager = SpawnManager(config, call_fn)
    result = manager.spawn(framework_name, spawn_input, mode_policy)
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, Future


FRAMEWORKS_DIR = os.path.expanduser("~/ora/frameworks/book/")
SPAWN_LOG_DIR = os.path.expanduser("~/ora/data/spawn-logs/")
DEFERRED_QUEUE = os.path.expanduser("~/ora/data/deferred-spawns.json")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SpawnPolicy:
    """Spawning policy extracted from a mode file."""
    local_sequential: str = "permitted"   # permitted, restricted, prohibited
    cloud_parallel: str = "restricted"    # permitted, restricted, prohibited
    deferred: str = "permitted"           # permitted, restricted, prohibited
    max_spawn_depth: int = 1              # subagents cannot spawn subagents
    max_concurrent_cloud: int = 2         # max parallel cloud dispatches
    restricted_frameworks: list[str] = field(default_factory=list)  # frameworks allowed when restricted
    prohibited_reason: str = ""           # why spawning is prohibited (for Signal 6)


@dataclass
class SpawnRequest:
    """A request to spawn a sub-framework."""
    framework_name: str
    input_text: str
    parent_session_id: str = ""
    parent_step: str = ""
    requested_mode: str = "auto"  # auto, local_sequential, cloud_parallel, deferred
    priority: str = "normal"      # essential, normal, supplementary
    context: dict = field(default_factory=dict)  # additional context for the framework


@dataclass
class HandoffPackage:
    """Structured result returned from a spawned framework execution."""
    framework_name: str
    execution_mode: str  # local_sequential, cloud_parallel, deferred, refused
    execution_time_seconds: float = 0.0
    success: bool = True
    summary: str = ""
    output_fields: dict = field(default_factory=dict)  # named output fields
    warnings: list[str] = field(default_factory=list)
    vault_reference: str = ""  # path if full output stored to vault
    token_consumption: dict = field(default_factory=dict)  # {model: tokens}
    signal_6_note: str = ""  # if refused, what analysis would have been performed


# ---------------------------------------------------------------------------
# Policy parsing
# ---------------------------------------------------------------------------

def parse_spawn_policy(mode_content: str) -> SpawnPolicy:
    """
    Extract spawning policy from a mode file.

    Looks for a SPAWNING POLICY section in the mode file with format:
    ### SPAWNING POLICY
    - local_sequential: permitted
    - cloud_parallel: restricted
    - deferred: permitted
    - max_spawn_depth: 1
    - max_concurrent_cloud: 2
    """
    import re

    policy = SpawnPolicy()

    # Find spawning policy section
    section_start = mode_content.find("### SPAWNING POLICY")
    if section_start == -1:
        # No explicit policy — use defaults
        return policy

    section = mode_content[section_start:]
    # Bound by next heading
    next_heading = re.search(r'\n#{2,3}\s+', section[len("### SPAWNING POLICY"):])
    if next_heading:
        section = section[:next_heading.start() + len("### SPAWNING POLICY")]

    # Parse key-value pairs
    for line in section.split('\n'):
        line = line.strip()
        if line.startswith('- local_sequential:'):
            policy.local_sequential = line.split(':', 1)[1].strip()
        elif line.startswith('- cloud_parallel:'):
            policy.cloud_parallel = line.split(':', 1)[1].strip()
        elif line.startswith('- deferred:'):
            policy.deferred = line.split(':', 1)[1].strip()
        elif line.startswith('- max_spawn_depth:'):
            try:
                policy.max_spawn_depth = int(line.split(':', 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith('- max_concurrent_cloud:'):
            try:
                policy.max_concurrent_cloud = int(line.split(':', 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith('- restricted_frameworks:'):
            frameworks_str = line.split(':', 1)[1].strip()
            policy.restricted_frameworks = [
                f.strip() for f in frameworks_str.split(',') if f.strip()
            ]
        elif line.startswith('- prohibited_reason:'):
            policy.prohibited_reason = line.split(':', 1)[1].strip()

    return policy


# ---------------------------------------------------------------------------
# Spawn Manager
# ---------------------------------------------------------------------------

class SpawnManager:
    """
    Manages sub-framework spawning during pipeline execution.

    Args:
        config: Endpoints configuration dict.
        call_fn: Model call function(messages, endpoint) -> str.
        current_depth: Current spawn depth (0 = root pipeline).
    """

    def __init__(self, config: dict = None, call_fn=None, current_depth: int = 0):
        self.config = config or {}
        self.call_fn = call_fn
        self.current_depth = current_depth
        self._active_cloud_spawns: list[Future] = []
        self._cloud_executor = None

    def spawn(self, request: SpawnRequest, policy: SpawnPolicy) -> HandoffPackage:
        """
        Execute a spawn request according to policy.

        Determines the appropriate execution mode and routes accordingly.

        Args:
            request: The spawn request.
            policy: The active mode's spawning policy.

        Returns:
            HandoffPackage with results or refusal.
        """
        # Check depth limit
        if self.current_depth >= policy.max_spawn_depth:
            return self._refuse(request, policy,
                                f"Spawn depth limit reached ({self.current_depth}/{policy.max_spawn_depth})")

        # Determine execution mode
        mode = self._resolve_mode(request, policy)

        if mode == "refused":
            return self._refuse(request, policy, policy.prohibited_reason or "Spawning prohibited by mode policy")

        # Load framework
        framework_text = self._load_framework(request.framework_name)
        if not framework_text:
            return self._refuse(request, policy,
                                f"Framework not found: {request.framework_name}")

        # Route to execution mode
        if mode == "local_sequential":
            return self._execute_local(request, framework_text, policy)
        elif mode == "cloud_parallel":
            return self._execute_cloud(request, framework_text, policy)
        elif mode == "deferred":
            return self._defer(request, framework_text, policy)

        return self._refuse(request, policy, f"Unknown execution mode: {mode}")

    def check_pending_cloud_spawns(self) -> list[HandoffPackage]:
        """
        Check for completed cloud spawn results.
        Called at pipeline checkpoints to inject results.
        """
        completed = []
        still_active = []

        for future in self._active_cloud_spawns:
            if future.done():
                try:
                    result = future.result(timeout=0)
                    completed.append(result)
                except Exception as e:
                    completed.append(HandoffPackage(
                        framework_name="unknown",
                        execution_mode="cloud_parallel",
                        success=False,
                        summary=f"Cloud spawn failed: {e}",
                    ))
            else:
                still_active.append(future)

        self._active_cloud_spawns = still_active
        return completed

    def get_deferred_queue(self) -> list[dict]:
        """Read the deferred spawn queue."""
        if not os.path.exists(DEFERRED_QUEUE):
            return []
        with open(DEFERRED_QUEUE, "r") as f:
            return json.load(f)

    def execute_deferred(self) -> list[HandoffPackage]:
        """Execute all deferred spawns. Called during maintenance or between sessions."""
        queue = self.get_deferred_queue()
        results = []

        for entry in queue:
            request = SpawnRequest(
                framework_name=entry["framework_name"],
                input_text=entry["input_text"],
                parent_session_id=entry.get("parent_session_id", ""),
                context=entry.get("context", {}),
            )
            framework_text = self._load_framework(request.framework_name)
            if framework_text:
                result = self._execute_local(
                    request, framework_text,
                    SpawnPolicy()  # use defaults for deferred execution
                )
                result.execution_mode = "deferred"
                results.append(result)

        # Clear queue
        if results:
            with open(DEFERRED_QUEUE, "w") as f:
                json.dump([], f)

        return results

    # -------------------------------------------------------------------
    # Execution modes
    # -------------------------------------------------------------------

    def _execute_local(self, request: SpawnRequest, framework_text: str,
                       policy: SpawnPolicy) -> HandoffPackage:
        """
        Mode A — Sequential Local execution.

        Parent completes current step, spawned framework runs as independent
        pipeline on local models, results returned as handoff package.
        """
        start_time = time.time()

        if not self.call_fn:
            return HandoffPackage(
                framework_name=request.framework_name,
                execution_mode="local_sequential",
                success=False,
                summary="No model call function available",
            )

        # Build the spawn prompt
        messages = self._build_spawn_messages(request, framework_text)

        # Get local endpoint
        endpoint = self._get_endpoint("depth")
        if not endpoint:
            endpoint = self._get_endpoint("breadth")
        if not endpoint:
            return HandoffPackage(
                framework_name=request.framework_name,
                execution_mode="local_sequential",
                success=False,
                summary="No local endpoint available",
            )

        # Execute
        response = self.call_fn(messages, endpoint)

        elapsed = time.time() - start_time

        # Parse response into handoff package
        package = self._parse_spawn_response(response, request.framework_name)
        package.execution_mode = "local_sequential"
        package.execution_time_seconds = elapsed

        # Log spawn
        self._log_spawn(request, package)

        return package

    def _execute_cloud(self, request: SpawnRequest, framework_text: str,
                       policy: SpawnPolicy) -> HandoffPackage:
        """
        Mode B — Parallel Cloud execution.

        Dispatch to commercial API while parent continues. Returns a
        placeholder handoff; actual results retrieved at next checkpoint.
        """
        # Check concurrent limit
        active_count = sum(1 for f in self._active_cloud_spawns if not f.done())
        if active_count >= policy.max_concurrent_cloud:
            # Fall back to deferred
            return self._defer(request, framework_text, policy)

        # Get cloud endpoint
        endpoint = self._get_cloud_endpoint()
        if not endpoint:
            return self._refuse(request, policy, "No cloud endpoint available")

        # Dispatch asynchronously
        if self._cloud_executor is None:
            self._cloud_executor = ThreadPoolExecutor(max_workers=policy.max_concurrent_cloud)

        messages = self._build_spawn_messages(request, framework_text)

        future = self._cloud_executor.submit(
            self._cloud_spawn_worker, messages, endpoint, request.framework_name
        )
        self._active_cloud_spawns.append(future)

        # Return placeholder
        return HandoffPackage(
            framework_name=request.framework_name,
            execution_mode="cloud_parallel",
            success=True,
            summary=f"Cloud spawn dispatched for {request.framework_name}. Results at next checkpoint.",
            warnings=["Results pending — check at next pipeline checkpoint"],
        )

    def _cloud_spawn_worker(self, messages: list, endpoint: dict,
                            framework_name: str) -> HandoffPackage:
        """Worker function for cloud spawn threads."""
        start_time = time.time()
        try:
            response = self.call_fn(messages, endpoint)
            elapsed = time.time() - start_time
            package = self._parse_spawn_response(response, framework_name)
            package.execution_mode = "cloud_parallel"
            package.execution_time_seconds = elapsed
            return package
        except Exception as e:
            return HandoffPackage(
                framework_name=framework_name,
                execution_mode="cloud_parallel",
                success=False,
                summary=f"Cloud spawn error: {e}",
                execution_time_seconds=time.time() - start_time,
            )

    def _defer(self, request: SpawnRequest, framework_text: str,
               policy: SpawnPolicy) -> HandoffPackage:
        """
        Mode C — Deferred execution.

        Queue the spawn for execution after the current pipeline run.
        """
        os.makedirs(os.path.dirname(DEFERRED_QUEUE), exist_ok=True)

        queue = self.get_deferred_queue()
        queue.append({
            "framework_name": request.framework_name,
            "input_text": request.input_text,
            "parent_session_id": request.parent_session_id,
            "parent_step": request.parent_step,
            "context": request.context,
            "queued_at": datetime.now().isoformat(),
            "priority": request.priority,
        })

        with open(DEFERRED_QUEUE, "w") as f:
            json.dump(queue, f, indent=2)

        return HandoffPackage(
            framework_name=request.framework_name,
            execution_mode="deferred",
            success=True,
            summary=f"Spawn deferred: {request.framework_name}. Queued for post-session execution.",
            warnings=["Results will be available in the next session"],
        )

    def _refuse(self, request: SpawnRequest, policy: SpawnPolicy,
                reason: str) -> HandoffPackage:
        """
        Mode D — Spawn refused.

        Returns Signal 6 flag noting what analysis would have been performed.
        """
        return HandoffPackage(
            framework_name=request.framework_name,
            execution_mode="refused",
            success=False,
            summary=f"Spawn refused: {reason}",
            signal_6_note=(
                f"Signal 6: Spawning constraint. Framework '{request.framework_name}' "
                f"would have provided additional analysis on: {request.input_text[:200]}. "
                f"Reason for refusal: {reason}"
            ),
        )

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    def _resolve_mode(self, request: SpawnRequest, policy: SpawnPolicy) -> str:
        """Determine the appropriate execution mode for a spawn request."""
        # Explicit mode request
        if request.requested_mode != "auto":
            mode = request.requested_mode
            policy_value = getattr(policy, mode, "prohibited")
            if policy_value == "prohibited":
                return "refused"
            if policy_value == "restricted":
                if request.framework_name not in policy.restricted_frameworks:
                    return "refused"
            return mode

        # Auto mode resolution
        # Essential priority → try local first, then cloud
        if request.priority == "essential":
            if policy.local_sequential in ("permitted", "restricted"):
                if policy.local_sequential == "restricted" and \
                   request.framework_name not in policy.restricted_frameworks:
                    pass  # Fall through to cloud
                else:
                    return "local_sequential"
            if policy.cloud_parallel in ("permitted", "restricted"):
                return "cloud_parallel"
            return "refused"

        # Normal priority → local if permitted, defer if not
        if policy.local_sequential == "permitted":
            return "local_sequential"
        if policy.local_sequential == "restricted" and \
           request.framework_name in policy.restricted_frameworks:
            return "local_sequential"
        if policy.deferred in ("permitted", "restricted"):
            return "deferred"

        # Supplementary priority → always defer
        if request.priority == "supplementary":
            if policy.deferred != "prohibited":
                return "deferred"
            return "refused"

        return "refused"

    def _build_spawn_messages(self, request: SpawnRequest,
                              framework_text: str) -> list[dict]:
        """Build the message list for a spawned framework execution."""
        system = (
            f"You are executing framework '{request.framework_name}' as a spawned sub-process.\n\n"
            f"FRAMEWORK SPECIFICATION:\n{framework_text}\n\n"
            f"EXECUTION CONTEXT:\n"
            f"- Parent session: {request.parent_session_id or 'unknown'}\n"
            f"- Parent step: {request.parent_step or 'unknown'}\n"
            f"- Priority: {request.priority}\n"
        )

        if request.context:
            system += f"- Additional context: {json.dumps(request.context)}\n"

        system += (
            "\nProduce a structured analysis following the framework specification. "
            "Output your results as a summary paragraph followed by named output fields."
        )

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": request.input_text},
        ]

    def _parse_spawn_response(self, response: str,
                              framework_name: str) -> HandoffPackage:
        """Parse a model response into a HandoffPackage."""
        if not response:
            return HandoffPackage(
                framework_name=framework_name,
                execution_mode="",
                success=False,
                summary="Empty response from model",
            )

        # Extract summary (first paragraph)
        paragraphs = response.strip().split('\n\n')
        summary = paragraphs[0] if paragraphs else response[:500]

        # Extract named output fields (look for "**Field:**" patterns)
        import re
        output_fields = {}
        for match in re.finditer(r'\*\*(.+?)\*\*:\s*(.+?)(?=\n\*\*|\n\n|$)',
                                 response, re.DOTALL):
            field_name = match.group(1).strip().lower().replace(' ', '_')
            field_value = match.group(2).strip()
            output_fields[field_name] = field_value

        return HandoffPackage(
            framework_name=framework_name,
            execution_mode="",
            success=True,
            summary=summary[:500],
            output_fields=output_fields,
        )

    def _load_framework(self, name: str) -> str | None:
        """Load a framework file from frameworks/book/."""
        # Try exact filename
        path = os.path.join(FRAMEWORKS_DIR, name)
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read()

        # Try with .md extension
        path = os.path.join(FRAMEWORKS_DIR, f"{name}.md")
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read()

        # Try matching by framework name prefix
        for fname in os.listdir(FRAMEWORKS_DIR):
            if fname.lower().startswith(name.lower().replace(' ', '-')):
                with open(os.path.join(FRAMEWORKS_DIR, fname), "r") as f:
                    return f.read()

        return None

    def _get_endpoint(self, slot: str) -> dict | None:
        """Get endpoint for a named slot."""
        try:
            from orchestrator.boot import get_slot_endpoint
            return get_slot_endpoint(self.config, slot)
        except ImportError:
            return None

    def _get_cloud_endpoint(self) -> dict | None:
        """Get a cloud (API) endpoint for parallel spawning."""
        endpoints = self.config.get("endpoints", [])
        for e in endpoints:
            if e.get("type") == "api" and e.get("status") == "active":
                return e
        return None

    def _log_spawn(self, request: SpawnRequest, package: HandoffPackage):
        """Log a spawn execution for cost accounting."""
        os.makedirs(SPAWN_LOG_DIR, exist_ok=True)

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "framework": request.framework_name,
            "mode": package.execution_mode,
            "success": package.success,
            "execution_time": package.execution_time_seconds,
            "parent_session": request.parent_session_id,
            "token_consumption": package.token_consumption,
        }

        log_file = os.path.join(
            SPAWN_LOG_DIR,
            f"spawn-{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        )

        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")


# ---------------------------------------------------------------------------
# Convenience functions for pipeline integration
# ---------------------------------------------------------------------------

def check_spawn_request(model_response: str) -> SpawnRequest | None:
    """
    Check if a model's response contains a spawn request.

    The model signals a spawn request using a structured format:
    <<<SPAWN_REQUEST>>>
    framework: [name]
    input: [text to analyze]
    priority: [essential|normal|supplementary]
    mode: [auto|local_sequential|cloud_parallel|deferred]
    <<<SPAWN_REQUEST_END>>>
    """
    import re

    match = re.search(
        r'<<<SPAWN_REQUEST>>>(.*?)<<<SPAWN_REQUEST_END>>>',
        model_response, re.DOTALL
    )
    if not match:
        return None

    block = match.group(1)
    framework = ""
    input_text = ""
    priority = "normal"
    mode = "auto"

    for line in block.strip().split('\n'):
        line = line.strip()
        if line.startswith('framework:'):
            framework = line.split(':', 1)[1].strip()
        elif line.startswith('input:'):
            input_text = line.split(':', 1)[1].strip()
        elif line.startswith('priority:'):
            priority = line.split(':', 1)[1].strip()
        elif line.startswith('mode:'):
            mode = line.split(':', 1)[1].strip()

    if framework:
        return SpawnRequest(
            framework_name=framework,
            input_text=input_text,
            requested_mode=mode,
            priority=priority,
        )
    return None


def inject_handoff_into_context(handoff: HandoffPackage) -> str:
    """
    Format a handoff package for injection into the parent pipeline's context.
    """
    if handoff.execution_mode == "refused":
        return f"\n[{handoff.signal_6_note}]\n"

    parts = [
        f"\n[SPAWNED FRAMEWORK RESULT: {handoff.framework_name}]",
        f"Mode: {handoff.execution_mode}",
        f"Time: {handoff.execution_time_seconds:.1f}s",
    ]

    if handoff.summary:
        parts.append(f"\n{handoff.summary}")

    if handoff.output_fields:
        parts.append("\nOutput fields:")
        for key, value in handoff.output_fields.items():
            parts.append(f"  {key}: {value[:200]}")

    if handoff.warnings:
        parts.append("\nWarnings:")
        for w in handoff.warnings:
            parts.append(f"  - {w}")

    if handoff.vault_reference:
        parts.append(f"\nFull output: {handoff.vault_reference}")

    parts.append(f"[END SPAWNED RESULT]\n")

    return "\n".join(parts)


if __name__ == "__main__":
    print("Spawning Protocol — Sub-Framework Execution Manager")
    print()
    print("Execution modes:")
    print("  A. Sequential Local — parent pauses, spawn runs on local models")
    print("  B. Parallel Cloud — dispatch to API while parent continues")
    print("  C. Deferred — queue for post-session execution")
    print("  D. Refused — Signal 6 noting what would have been analyzed")
    print()
    print("Policy levels: permitted, restricted (named frameworks only), prohibited")
    print(f"Deferred queue: {DEFERRED_QUEUE}")
    print(f"Spawn logs: {SPAWN_LOG_DIR}")
