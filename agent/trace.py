"""Tool-call tracing for the agent loop.

Per phase3_architecture.md §2.8 — every tool call and result is captured
during a question, surfaced at the end. Phase 3A: print to stdout in
plain text. Phase 3C: same data feeds the web UI's "How did I get this
answer?" expandable section.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """One tool invocation: what the agent asked for, what came back."""
    tool_name: str
    tool_input: dict[str, Any]
    tool_output: Any


@dataclass
class Trace:
    """All tool calls made during a single user question."""
    calls: list[ToolCall] = field(default_factory=list)

    def record(self, tool_name: str, tool_input: dict[str, Any], tool_output: Any) -> None:
        self.calls.append(ToolCall(tool_name, tool_input, tool_output))

    def render(self) -> str:
        """Plain-text trace summary for terminal display."""
        if not self.calls:
            return "(no tool calls)"
        lines = []
        for i, call in enumerate(self.calls, 1):
            lines.append(f"[{i}] {call.tool_name}")
            if call.tool_name == "run_sql":
                query = call.tool_input.get("query", "").strip()
                lines.append(f"    SQL: {query}")
                out = call.tool_output
                if isinstance(out, dict):
                    if out.get("ok"):
                        rc = out.get("row_count", 0)
                        trunc = " (truncated)" if out.get("truncated") else ""
                        lines.append(f"    -> {rc} row(s){trunc}")
                        for row in out.get("rows", [])[:5]:
                            lines.append(f"       {row}")
                        if rc > 5:
                            lines.append(f"       ... ({rc - 5} more)")
                    else:
                        lines.append(
                            f"    -> ERROR {out.get('error_type')}: "
                            f"{out.get('error_message')}"
                        )
            else:
                lines.append(f"    input:  {call.tool_input}")
                lines.append(f"    output: {call.tool_output}")
        return "\n".join(lines)

    def serialize(self) -> list[dict[str, Any]]:
        """Structured trace for JSON output (web /chat response, future eval).

        Returns one dict per call with tool_name, tool_input, tool_output.
        Tool outputs are already JSON-prepared by the tool implementations
        (see _to_json_safe in tools.py for run_sql).
        """
        return [
            {
                "tool_name": call.tool_name,
                "tool_input": call.tool_input,
                "tool_output": call.tool_output,
            }
            for call in self.calls
        ]
