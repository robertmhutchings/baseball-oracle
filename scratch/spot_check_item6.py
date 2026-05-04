"""Item 6 spot-checks — three questions targeting the new Schema gotchas section.

Run:
    C:\\BaseballOracle\\.venv\\Scripts\\python.exe scratch\\spot_check_item6.py

Mirrors agent.main.answer_question but non-interactive: ask_user calls return a
canned "no follow-up available" so the agent can keep going. We're testing
whether the gotchas in the prompt actually take, not exercising disambiguation.
"""

import json
import sys

import anthropic

from agent.config import MAX_AGENT_TURNS, MODEL, get_anthropic_api_key
from agent.prompts import SYSTEM_PROMPT
from agent.tools import TOOL_IMPLS, TOOL_SPECS
from agent.trace import Trace


def answer_noninteractive(client: anthropic.Anthropic, question: str) -> tuple[str, Trace]:
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
            return last_text + f"\n[stop_reason={response.stop_reason!r}]", trace

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tu in tool_uses:
            if tu.name == "ask_user":
                output = {
                    "user_response": (
                        "(no follow-up available — answer with what you have, "
                        "and note the ambiguity if relevant)"
                    )
                }
            else:
                impl = TOOL_IMPLS.get(tu.name)
                if impl is None:
                    output = {
                        "ok": False,
                        "error_type": "UnknownTool",
                        "error_message": f"No implementation for {tu.name!r}",
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

    return last_text + f"\n[exceeded MAX_AGENT_TURNS={MAX_AGENT_TURNS}]", trace


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    client = anthropic.Anthropic(api_key=get_anthropic_api_key())

    questions = [
        ("Switch-hitters in 1998 (item 13)",
         "How many switch-hitters played in 1998?"),
        ("Pitch sequence length in 2010 (items 3+11+15)",
         "What was the longest pitch sequence in a 2010 at-bat?"),
        ("1998 WS Game 1 start time (item 16)",
         "What time did the 1998 World Series Game 1 start?"),
    ]

    for i, (label, q) in enumerate(questions, 1):
        print(f"\n{'=' * 70}")
        print(f"SPOT CHECK {i}: {label}")
        print(f"Q: {q}")
        print('=' * 70)
        try:
            response, trace = answer_noninteractive(client, q)
            print("\n--- RESPONSE ---")
            print(response or "(no response)")
            print("\n--- TRACE ---")
            print(trace.render())
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
