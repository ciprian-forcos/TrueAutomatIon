"""
The Oracle: Routes coding tasks to the cheapest capable model.

Levels:
  L1 (local 1.5B)  - File ops, simple lookups, formatting
  L2 (local 7B)    - Unit tests, boilerplate, simple functions
  L3 (Grok cloud)  - Feature implementation, debugging, multi-file changes
  L4 (Opus cloud)  - Architecture, complex refactors, system design
"""

import os
import sys
import re
import litellm

# Point at your LiteLLM proxy
PROXY_BASE = "http://localhost:4000"
PROXY_KEY = os.environ.get(
    "LITELLM_MASTER_KEY",
    "sk-litellm-master-change-this-to-something-random"
)

# ── Heuristic Classification ──────────────────────────────────────────

L1_SIGNALS = [
    "list files", "what does this command", "show me", "find file",
    "rename", "move", "copy", "delete", "ls", "cat", "grep", "dir",
    "format this", "convert", "what is", "explain this error",
]

L2_SIGNALS = [
    "write a test", "unit test", "write a function", "boilerplate",
    "add a method", "css", "html", "simple script", "regex",
    "parse", "validate", "serialize", "type definition",
]

L4_SIGNALS = [
    "architect", "design", "system design", "refactor the entire",
    "breaking change", "migration strategy", "redesign",
    "evaluate tradeoffs", "review this architecture",
    "spec", "technical requirements", "interface design",
]


def count_context_files(messages: list) -> int:
    """Estimate how many files are included in the context."""
    full_text = " ".join(m.get("content", "") for m in messages)
    fences = len(re.findall(r"```", full_text)) // 2
    file_refs = len(re.findall(r"[\w/\\]+\.\w{1,5}", full_text))
    return max(fences, file_refs // 3)


def estimate_tokens(messages: list) -> int:
    """Quick token count estimate."""
    text = " ".join(m.get("content", "") for m in messages)
    return len(text) // 4


def classify(prompt: str, messages: list) -> tuple:
    """Returns (level_name, model_name, reason)."""
    prompt_lower = prompt.lower()
    token_count = estimate_tokens(messages)
    file_count = count_context_files(messages)

    # Rule 1: Large context → skip local (too slow on CPU)
    if file_count > 3 or token_count > 8000:
        if any(kw in prompt_lower for kw in L4_SIGNALS):
            return ("L4", "l4-architect",
                    f"Large context ({file_count} files, ~{token_count} tokens) + architecture signals")
        return ("L3", "l3-senior",
                f"Large context ({file_count} files, ~{token_count} tokens) -> cloud")

    # Rule 2: Architecture signals → L4
    if any(kw in prompt_lower for kw in L4_SIGNALS):
        return ("L4", "l4-architect", "Architecture/design task detected")

    # Rule 3: Simple signals → L1
    if any(kw in prompt_lower for kw in L1_SIGNALS):
        return ("L1", "l1-intern", "Simple lookup/command task")

    # Rule 4: Coding signals → L2
    if any(kw in prompt_lower for kw in L2_SIGNALS):
        return ("L2", "l2-junior", "Standard coding task, local model capable")

    # Rule 5: Default → L3
    return ("L3", "l3-senior", "No strong signals, defaulting to cloud senior")


# ── Execution ─────────────────────────────────────────────────────────

def route_and_execute(prompt: str, messages: list = None, max_retries_local: int = 2):
    """
    Classify, route, execute. Implements the "two-strike" rule:
    if a local model fails twice, escalate to cloud.
    """
    if messages is None:
        messages = [{"role": "user", "content": prompt}]

    level, model, reason = classify(prompt, messages)
    print(f"[Oracle] {level} -> {model} | Reason: {reason}")

    for attempt in range(1, max_retries_local + 1):
        try:
            response = litellm.completion(
                model=model,
                messages=messages,
                api_base=PROXY_BASE,
                api_key=PROXY_KEY,
                timeout=120,
            )
            content = response.choices[0].message.content
            print(f"[Oracle] Success on attempt {attempt}")
            return {"level": level, "model": model, "content": content}

        except Exception as e:
            print(f"[Oracle] Attempt {attempt} failed: {e}")

            # Two-strike rule: local models get 2 tries, then escalate
            if level in ("L1", "L2") and attempt >= max_retries_local:
                print("[Oracle] Escalating to L3 (cloud)...")
                model = "l3-senior"
                level = "L3"
                try:
                    response = litellm.completion(
                        model=model,
                        messages=messages,
                        api_base=PROXY_BASE,
                        api_key=PROXY_KEY,
                        timeout=300,
                    )
                    content = response.choices[0].message.content
                    return {"level": level, "model": model, "content": content}
                except Exception as e2:
                    return {"level": level, "model": model, "error": str(e2)}

    return {"level": level, "model": model, "error": "All attempts failed"}


# ── CLI Interface ─────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    else:
        prompt = input("Enter your prompt: ")

    result = route_and_execute(prompt)

    if "error" in result:
        print(f"\n[ERROR] {result['error']}")
    else:
        print(f"\n--- Response from {result['level']} ({result['model']}) ---")
        print(result["content"])
