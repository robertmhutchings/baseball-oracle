"""Baseball Oracle — agent REPL.

Phase 3A Step 2: minimal interactive loop. Read a question, send to Claude
with the run_sql tool, handle tool_use rounds until end_turn, print the
final response and tool trace, prompt for the next question.

Each question runs with fresh conversation history. Multi-question
conversational memory ("and what about June?") is deferred to Phase 3C
when we have the web UI.

Run:
    C:\\BaseballOracle\\.venv\\Scripts\\python.exe -m agent.main
"""

import json
import sys

import anthropic

from agent.config import MAX_AGENT_TURNS, MODEL, get_anthropic_api_key
from agent.prompts import SYSTEM_PROMPT
from agent.tools import TOOL_IMPLS, TOOL_SPECS
from agent.trace import Trace


EXIT_COMMANDS = {":quit", ":exit", ":q"}


class UserAbortedQuestion(Exception):
    """Raised when the user types :quit (or equivalent) during an ask_user
    round. The REPL catches this, cancels the current question, and returns
    to the top-level prompt without exiting."""


def answer_question(client: anthropic.Anthropic, question: str) -> tuple[str, Trace]:
    """Run one question through the agent loop.

    Returns (final_response_text, trace).
    """
    trace = Trace()
    messages: list[dict] = [{"role": "user", "content": question}]
    last_text = ""

    for _turn in range(MAX_AGENT_TURNS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_SPECS,
            messages=messages,
        )

        text_this_turn: list[str] = []
        tool_uses = []
        for block in response.content:
            if block.type == "text":
                text_this_turn.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)
        last_text = "\n".join(text_this_turn).strip()

        if response.stop_reason == "end_turn":
            return last_text, trace

        if response.stop_reason != "tool_use":
            note = f"\n[agent stopped unexpectedly: stop_reason={response.stop_reason!r}]"
            return (last_text + note).strip(), trace

        # Append the assistant turn (must include tool_use blocks for the
        # API to accept the next user turn with tool_results).
        messages.append({"role": "assistant", "content": response.content})

        # Execute each tool, record in trace, build tool_result blocks.
        # ask_user is special: it routes to the REPL user, not TOOL_IMPLS.
        tool_results = []
        for tu in tool_uses:
            if tu.name == "ask_user":
                user_question = (tu.input.get("question") or "").strip()
                print()
                print(f"Oracle: {user_question}")
                user_reply = input("> ").strip()
                if user_reply.lower() in EXIT_COMMANDS:
                    raise UserAbortedQuestion()
                output = {"user_response": user_reply}
            else:
                impl = TOOL_IMPLS.get(tu.name)
                if impl is None:
                    output = {
                        "ok": False,
                        "error_type": "UnknownTool",
                        "error_message": f"No implementation for tool {tu.name!r}",
                    }
                else:
                    output = impl(**tu.input)
            trace.record(tu.name, dict(tu.input), output)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": json.dumps(output, default=str),
            })

        messages.append({"role": "user", "content": tool_results})

    # Loop exhausted — runaway-loop guard tripped.
    return (
        last_text + f"\n\n[agent stopped: exceeded MAX_AGENT_TURNS={MAX_AGENT_TURNS}]"
    ).strip(), trace


def repl() -> int:
    # Force UTF-8 on the Windows console — em dashes etc. would otherwise
    # mojibake under the default cp1252 encoding.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    # Validate API key up front so the failure mode is "won't start" rather
    # than "crashes mid-question."
    try:
        api_key = get_anthropic_api_key()
    except RuntimeError as e:
        print(f"Startup error: {e}", file=sys.stderr)
        return 1

    client = anthropic.Anthropic(api_key=api_key)

    print("Baseball Oracle — Phase 3A REPL")
    print(f"Model: {MODEL}")
    print("Ask a question. Type :quit, :exit, or Ctrl+C to leave.")
    print()

    while True:
        try:
            question = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return 0

        if not question:
            continue
        if question.lower() in EXIT_COMMANDS:
            return 0

        try:
            response_text, trace = answer_question(client, question)
        except UserAbortedQuestion:
            print("\n[question abandoned; returning to prompt]")
            continue
        except KeyboardInterrupt:
            print("\n[interrupted; returning to prompt]")
            continue
        except EOFError:
            # User closed stdin (Ctrl+Z on Windows). Exit the REPL cleanly,
            # matching top-level EOF behavior.
            print()
            return 0
        except Exception as e:
            print(f"\n[error: {type(e).__name__}: {e}]\n", file=sys.stderr)
            continue

        print()
        print(response_text or "(no response)")
        print()
        print("--- trace ---")
        print(trace.render())
        print()


if __name__ == "__main__":
    sys.exit(repl())
