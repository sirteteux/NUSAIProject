"""
react_engine.py — Shared ReAct (Reasoning + Acting) loop engine.

All five domain agents import and use run_react_loop().

Fixes applied vs previous version:
  1. Final Answer detection uses regex to handle markdown variants
     (**Final Answer**, **Final Answer:**, Final Answer:, etc.)
  2. When no tool calls and no Final Answer marker, the fallback strips
     the Thought/Action/Observation trace before returning to the user
  3. REACT_INSTRUCTION now explicitly bans markdown on the Final Answer line
  4. Thoughts are stored separately and never shown to the user
"""

import re
import json
import logging
from typing import List, Dict, Callable, Awaitable, Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# ReAct system prompt fragment
# ─────────────────────────────────────────────────────────────────────────────
REACT_INSTRUCTION = """
## ReAct Reasoning Protocol

You are a ReAct agent. Follow this cycle for every request:

Thought: Before calling any tool, reason explicitly:
  - What do I already know?
  - What do I still need to fully answer?
  - Has my goal been achieved? (yes / no)

Action: If goal NOT achieved → call the appropriate tool.

Observation: After receiving tool results, reason about what you learned.
  Continue Thought → Action → Observation as needed.

Final Answer: When goal IS achieved, write your complete user-facing response
  on a line beginning with exactly these two words and a colon:
  Final Answer: <your response here>

CRITICAL RULES:
- NEVER use markdown bold (**) on the Final Answer line
- The Final Answer line must start with exactly: Final Answer:
- NEVER show Thought / Action / Observation text to the user
- Only the text after "Final Answer:" is shown to the user
- NEVER call a tool without a preceding Thought
- If a tool returns an error, reason about an alternative approach
"""

REEVAL_PROMPT = (
    "Observations received. Continue your ReAct cycle:\n\n"
    "Thought: What did I learn? Is my goal now fully achieved?\n\n"
    "- YES → write: Final Answer: <your complete response>\n"
    "- NO  → state what is still missing, then call the next tool."
)

# ─────────────────────────────────────────────────────────────────────────────
# Final Answer extraction — robust to markdown formatting variants
# Matches any of:
#   Final Answer: ...
#   **Final Answer**: ...
#   **Final Answer:** ...
#   Final Answer — ...
# ─────────────────────────────────────────────────────────────────────────────
FINAL_ANSWER_MARKER = "Final Answer:"   # kept for coordinator compatibility

_FINAL_ANSWER_RE = re.compile(
    r'\*{0,2}Final Answer\*{0,2}\s*[:\-–]\s*',
    re.IGNORECASE
)

# Labels the model writes into its thinking trace — strip these from fallback answers
_TRACE_LABELS_RE = re.compile(
    r'^\*{0,2}(Thought|Action|Observation)\*{0,2}\s*[:\-–]',
    re.MULTILINE | re.IGNORECASE
)


def _extract_final_answer(text: str) -> str | None:
    """
    Return the text after any Final Answer marker variant.
    Returns None if no marker is found.
    """
    match = _FINAL_ANSWER_RE.search(text)
    if match:
        return text[match.end():].strip()
    return None


def _strip_trace(text: str) -> str:
    """
    Remove Thought / Action / Observation labels and their content
    from a string so the reasoning trace is never shown to users.
    Keeps only lines that don't begin with a trace label.
    """
    # Split into sections at each trace label
    parts = _TRACE_LABELS_RE.split(text)
    # parts[0] is text before the first label (may be empty)
    # Everything that is NOT a label name we keep — but since split()
    # returns the captured groups too, we only want even-indexed parts
    # Actually re.split with a capturing group interleaves label names.
    # Simpler: just remove everything from first label to Final Answer marker.
    fa_match = _FINAL_ANSWER_RE.search(text)
    if fa_match:
        return text[fa_match.end():].strip()

    # No Final Answer marker — return lines that don't start with a label
    clean_lines = []
    for line in text.splitlines():
        if not _TRACE_LABELS_RE.match(line.strip()):
            clean_lines.append(line)
    return "\n".join(clean_lines).strip()


# ─────────────────────────────────────────────────────────────────────────────
# Main ReAct loop
# ─────────────────────────────────────────────────────────────────────────────
async def run_react_loop(
    openai_client: Any,
    messages: List[Dict],
    tools: List[Dict],
    tool_executor: Callable[[str, Dict], Awaitable[str]],
    service_name: str,
    max_iterations: int = 8,
) -> Dict:
    """
    Run a ReAct loop until the model produces a Final Answer or
    the iteration limit is reached.

    Returns:
        answer      — clean user-facing text (no trace labels)
        tools_used  — ordered list of tool names called
        thoughts    — raw reasoning trace (for audit logs only)
        iterations  — number of cycles completed
    """
    tools_used = []
    thoughts   = []

    for iteration in range(max_iterations):
        logger.info(f"🔄 [{service_name}] ReAct iteration {iteration + 1}/{max_iterations}")

        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.2,
            max_tokens=900
        )

        msg          = response.choices[0].message
        thought_text = msg.content or ""

        if thought_text:
            # Store raw trace for audit — never shown to user
            thoughts.append(thought_text)
            logger.info(f"💭 [{service_name}] Trace: {thought_text[:200]}")

            # ── Check for Final Answer (handles all markdown variants) ────────
            answer = _extract_final_answer(thought_text)
            if answer is not None:
                logger.info(
                    f"✅ [{service_name}] Final Answer at iteration {iteration + 1}. "
                    f"Tools: {tools_used}"
                )
                return {
                    "answer":     answer,
                    "tools_used": tools_used,
                    "thoughts":   thoughts,
                    "iterations": iteration + 1,
                }

        # Append assistant message before checking tool calls
        messages.append(msg)

        # ── No tool calls and no Final Answer ─────────────────────────────────
        # Fallback: strip the trace labels and return whatever clean text remains.
        # A well-prompted model should always use "Final Answer:" — this path
        # fires only if the model forgets the protocol.
        if not msg.tool_calls:
            clean = _strip_trace(thought_text) if thought_text else ""
            if not clean:
                clean = "I was unable to complete the reasoning. Please try rephrasing or contact HR at hr@company.com."
            logger.warning(
                f"⚠️ [{service_name}] No tool calls and no Final Answer marker "
                f"at iteration {iteration + 1}. Returning stripped content."
            )
            return {
                "answer":     clean,
                "tools_used": tools_used,
                "thoughts":   thoughts,
                "iterations": iteration + 1,
            }

        # ── Execute tool calls ────────────────────────────────────────────────
        for tool_call in msg.tool_calls:
            tool_name = tool_call.function.name
            try:
                tool_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            logger.info(f"🔧 [{service_name}] Action → {tool_name}({tool_args})")
            tool_result = await tool_executor(tool_name, tool_args)
            tools_used.append(tool_name)
            logger.info(f"📊 [{service_name}] Observation ← {tool_name}: {str(tool_result)[:120]}")

            messages.append({
                "role":         "tool",
                "tool_call_id": tool_call.id,
                "content":      tool_result
            })

        # ── Re-evaluation after observations ──────────────────────────────────
        messages.append({"role": "user", "content": REEVAL_PROMPT})

    # ── Max iterations reached ────────────────────────────────────────────────
    logger.warning(f"⚠️ [{service_name}] Max iterations ({max_iterations}) reached.")
    return {
        "answer": (
            "I reached the maximum reasoning depth. "
            "Please try a more specific question or contact HR at hr@company.com."
        ),
        "tools_used": tools_used,
        "thoughts":   thoughts,
        "iterations": max_iterations,
    }


def build_react_system_prompt(agent_system_prompt: str) -> str:
    """Prepend ReAct instruction to any agent's system prompt."""
    return f"{REACT_INSTRUCTION}\n\n---\n\n{agent_system_prompt}"