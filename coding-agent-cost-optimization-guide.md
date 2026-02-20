# The 4-Level AI Coding Agent: Cost Optimization Guide

**Author:** Ciprian Forcos | **Date:** February 2026
**Hardware:** i7-1370P (20 threads), 32GB RAM, no dedicated GPU, Windows 10/11 (native)

---

## Overview

This guide sets up a 4-level AI routing architecture that sends each coding task to the cheapest model capable of handling it. Local models handle trivial work for free, cheap cloud APIs handle implementation, and expensive frontier models handle architecture — only when needed.

Everything runs natively on Windows — no WSL2. This ensures direct filesystem access for Phase 2 (UiPath Assistant integration).

### Cost Comparison

| Level | Role | Model | Cost per 1M tokens (in/out) |
|-------|------|-------|-----------------------------|
| L1 | Intern | Qwen 2.5 1.5B (local) | $0 / $0 |
| L2 | Junior Dev | Qwen 2.5 Coder 7B (local) | $0 / $0 |
| L3 | Senior Dev | Grok 4.1 Fast Reasoning (cloud) | $0.20 / ~$1.00 |
| L4 | Architect | Claude Opus 4.5 (cloud) | $5.00 / $25.00 |

### RAM Budget

- **System (Windows, Chrome, IDE):** ~20 GB
- **AI models (Ollama):** ~6 GB max
- **Buffer:** ~6 GB free

---

## Part 1: Prerequisites (Windows Native)

### 1.1 Install Ollama for Windows

1. Download `OllamaSetup.exe` from [ollama.com/download](https://ollama.com/download)
2. Run the installer (no admin required — installs to your user directory)
3. Ollama starts automatically and runs in the system tray

Verify in PowerShell or Command Prompt:

```powershell
ollama --version
```

### 1.2 Install Docker Desktop for Windows

1. Download from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)
2. Run the installer, enable WSL2 backend when prompted (this is Docker's internal requirement, your projects still live on Windows)
3. Restart your PC
4. Open Docker Desktop, wait for it to start

Verify:

```powershell
docker --version
docker compose version
```

### 1.3 Install Python 3.10+

If not already installed:

1. Download from [python.org/downloads](https://www.python.org/downloads/)
2. **Check "Add Python to PATH"** during install
3. Verify:

```powershell
python --version
pip --version
```

### 1.4 Get API Keys

You need two API keys:

1. **Anthropic:** Go to [console.anthropic.com](https://console.anthropic.com) → API Keys → Create Key
2. **xAI (Grok):** Go to [console.x.ai](https://console.x.ai) → API Keys → Create Key

Save these — you'll add them to your `.env` file in Part 3.

---

## Part 2: Local Models (Ollama)

### 2.1 Pull the Models

Open PowerShell:

```powershell
# Level 1: The Intern (1.2 GB RAM)
ollama pull qwen2.5:1.5b

# Level 2: The Junior Dev (4.8 GB RAM, Q4 quantized)
ollama pull qwen2.5-coder:7b
```

### 2.2 Configure Ollama for Always-On

Set Windows environment variables so Ollama keeps models loaded and allows connections from Docker:

1. Open **Settings** → search **"environment variables"** → click **"Edit environment variables for your account"**
2. Add these user variables:

| Variable | Value | Purpose |
|----------|-------|---------|
| `OLLAMA_KEEP_ALIVE` | `-1` | Keep models in RAM indefinitely |
| `OLLAMA_HOST` | `0.0.0.0:11434` | Allow Docker containers to connect |
| `OLLAMA_ORIGINS` | `*` | Allow cross-origin requests (needed for LiteLLM/Cursor) |

3. Click OK, then **restart Ollama** (right-click tray icon → Quit, then relaunch from Start Menu)

### 2.3 Pre-load the L1 Model

```powershell
# Load the Intern and keep it in RAM
ollama run qwen2.5:1.5b --keepalive -1
```

Type `/bye` to exit the chat. The model stays loaded in memory.

> **Tip:** With `OLLAMA_KEEP_ALIVE=-1` set globally, any model you use will stay loaded until you explicitly unload it or Ollama restarts. To unload: `ollama stop qwen2.5:1.5b`

### 2.4 Test Local Models

```powershell
# Test L1 (should respond in 1-2 seconds)
curl http://localhost:11434/api/chat -d "{\"model\": \"qwen2.5:1.5b\", \"messages\": [{\"role\": \"user\", \"content\": \"List files in a directory using PowerShell\"}], \"stream\": false}"

# Test L2 (should respond in 5-15 seconds on i7 CPU)
curl http://localhost:11434/api/chat -d "{\"model\": \"qwen2.5-coder:7b\", \"messages\": [{\"role\": \"user\", \"content\": \"Write a Python function to check if a number is prime\"}], \"stream\": false}"
```

> **Note:** Windows `curl` requires escaped double quotes (`\"`). If using PowerShell, you can also use `Invoke-RestMethod` instead.

If the 7B model takes >30s per response, your system is memory-constrained. In that case, stick with L1 locally and route L2 tasks to L3 (Grok) instead.

---

## Part 3: LiteLLM Proxy (Docker)

### 3.1 Create Project Directory

```powershell
mkdir C:\litellm-proxy
cd C:\litellm-proxy
```

### 3.2 Create the Environment File

Create `C:\litellm-proxy\.env` in any text editor (VS Code recommended). Make sure to save with **UTF-8 encoding** and **LF line endings**:

```
LITELLM_MASTER_KEY=sk-litellm-master-change-this-to-something-random
ANTHROPIC_API_KEY=sk-ant-your-actual-key-here
XAI_API_KEY=xai-your-actual-key-here
```

### 3.3 Create the LiteLLM Config

Create `C:\litellm-proxy\config.yaml`:

```yaml
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY

litellm_settings:
  drop_params: true
  num_retries: 2
  request_timeout: 300

model_list:
  # ============================================
  # LEVEL 1: The Intern (Local, Free)
  # ============================================
  - model_name: l1-intern
    litellm_params:
      model: ollama/qwen2.5:1.5b
      api_base: "http://host.docker.internal:11434"
      tpm: 5000

  # ============================================
  # LEVEL 2: Junior Dev (Local, Free)
  # ============================================
  - model_name: l2-junior
    litellm_params:
      model: ollama/qwen2.5-coder:7b
      api_base: "http://host.docker.internal:11434"
      tpm: 3000

  # ============================================
  # LEVEL 3: Senior Dev (Grok, Cheap)
  # ============================================
  - model_name: l3-senior
    litellm_params:
      model: xai/grok-4-1-fast-reasoning
      api_key: os.environ/XAI_API_KEY
      timeout: 300
      max_retries: 2

  # ============================================
  # LEVEL 4: Architect (Claude Opus, Expensive)
  # ============================================
  - model_name: l4-architect
    litellm_params:
      model: anthropic/claude-opus-4-5-20251101
      api_key: os.environ/ANTHROPIC_API_KEY
      timeout: 300
      max_retries: 1

  # ============================================
  # CONVENIENCE ALIASES
  # ============================================
  # "default" routes to Grok (best cost/quality ratio)
  - model_name: default
    litellm_params:
      model: xai/grok-4-1-fast-reasoning
      api_key: os.environ/XAI_API_KEY
      timeout: 300

  # Claude Sonnet for mid-tier tasks
  - model_name: l3-sonnet
    litellm_params:
      model: anthropic/claude-sonnet-4-5-20250929
      api_key: os.environ/ANTHROPIC_API_KEY
      timeout: 300

# Fallback chains
fallbacks:
  - {l2-junior: [l3-senior]}
  - {l3-senior: [l3-sonnet]}
  - {l4-architect: [l3-senior]}
```

> **`host.docker.internal`** is natively supported by Docker Desktop on Windows. It resolves to your Windows host IP, letting the LiteLLM container reach Ollama running on your machine. No extra config needed.

### 3.4 Create Docker Compose File

Create `C:\litellm-proxy\docker-compose.yml`:

```yaml
version: '3.8'

services:
  litellm:
    image: litellm/litellm:main-latest
    env_file:
      - .env
    volumes:
      - ./config.yaml:/app/config.yaml
    ports:
      - "4000:4000"
    command: ["--config", "/app/config.yaml", "--port", "4000"]
    dns:
      - 8.8.8.8
      - 1.1.1.1
    restart: unless-stopped
```

> **Why no `extra_hosts` or `host-gateway`?** Docker Desktop for Windows resolves `host.docker.internal` automatically. No manual mapping needed.

> **Why no PostgreSQL?** You don't need it to start. The database is only required for budget tracking across restarts. You can add it later (see Part 7). For now, in-memory tracking is fine.

### 3.5 Start LiteLLM

```powershell
cd C:\litellm-proxy
docker compose up -d
```

### 3.6 Verify Everything Works

```powershell
# Check it's running
docker ps

# List available models
curl http://localhost:4000/models -H "Authorization: Bearer sk-litellm-master-change-this-to-something-random"

# Test L1 (local, should be instant)
curl http://localhost:4000/v1/chat/completions -H "Authorization: Bearer sk-litellm-master-change-this-to-something-random" -H "Content-Type: application/json" -d "{\"model\": \"l1-intern\", \"messages\": [{\"role\": \"user\", \"content\": \"Hello\"}]}"

# Test L3 (Grok cloud)
curl http://localhost:4000/v1/chat/completions -H "Authorization: Bearer sk-litellm-master-change-this-to-something-random" -H "Content-Type: application/json" -d "{\"model\": \"l3-senior\", \"messages\": [{\"role\": \"user\", \"content\": \"Hello\"}]}"

# Test L4 (Opus cloud)
curl http://localhost:4000/v1/chat/completions -H "Authorization: Bearer sk-litellm-master-change-this-to-something-random" -H "Content-Type: application/json" -d "{\"model\": \"l4-architect\", \"messages\": [{\"role\": \"user\", \"content\": \"Hello\"}]}"
```

If all return responses, your proxy is working.

---

## Part 4: The Oracle (Task Router)

This is a standalone Python script that classifies tasks and routes them to the right level. It uses **simple heuristics, not an ML model** — faster, cheaper, and easier to debug.

### 4.1 Install Dependencies

```powershell
pip install litellm tiktoken
```

### 4.2 The Oracle Script

Save as `C:\litellm-proxy\oracle.py`:

```python
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
```

### 4.3 Test the Oracle

```powershell
cd C:\litellm-proxy

# Should route to L1
python oracle.py "list all files in the src directory"

# Should route to L2
python oracle.py "write a unit test for a factorial function"

# Should route to L3 (default)
python oracle.py "fix the authentication bug in the login handler"

# Should route to L4
python oracle.py "design the architecture for a plugin system with hot reloading"
```

### 4.4 Customizing the Oracle

The keyword lists are starting points. As you use the system, you'll notice misroutes. Tuning is simple:

- Task went to L3 but L2 could have handled it → add keywords to `L2_SIGNALS`
- Task went to L1 but failed → add keywords to `L2_SIGNALS` or remove from `L1_SIGNALS`
- Adjust `file_count` and `token_count` thresholds as needed

The beauty of heuristic routing: it's a 5-second edit, not a model retrain.

---

## Part 5: Cursor Configuration

### 5.1 Point Cursor at LiteLLM

In Cursor:

1. Press `Ctrl + ,` to open Settings
2. Click **Models** in the left sidebar
3. Toggle on **"Override OpenAI Base URL (when using key)"**
4. Set the base URL to: `http://localhost:4000/v1`
5. Paste your `LITELLM_MASTER_KEY` as the OpenAI API key
6. Add your model names (`l1-intern`, `l2-junior`, `l3-senior`, `l4-architect`) to the model list
7. **Deselect** all other models (OpenAI, Anthropic native, etc.) to avoid validation errors

Now any model name you type in Cursor gets routed through LiteLLM.

### 5.2 Recommended Model Assignments in Cursor

| Cursor Feature | Model Name | Why |
|----------------|------------|-----|
| Tab completion | `l1-intern` | Instant, free |
| Inline edit (Ctrl+K) | `l2-junior` | Fast, free, good for single-function edits |
| Chat | `l3-senior` | Grok handles conversational coding well |
| Agent mode | `l3-senior` | Default to cheap; manually switch to `l4-architect` for hard problems |

> **Tip:** You can type any model name from your LiteLLM config directly in Cursor's model selector. Use `l4-architect` sparingly — only for genuine architecture work.

---

## Part 6: The Architect Workflow (Opus → Grok Handoff)

This is for when you need Opus-quality design but don't want to pay Opus prices for implementation.

### 6.1 The Handoff Spec Format

When L4 (Opus) designs something, have it output a structured spec that L3 (Grok) can implement mechanically:

```markdown
# Implementation Spec: [Feature Name]

## Module Purpose
[One sentence describing what this module does]

## File Structure
- src/auth/token-manager.ts
- src/auth/token-manager.test.ts
- src/auth/types.ts

## Interfaces (exact signatures)
```typescript
interface TokenManager {
  generate(userId: string, scopes: string[]): Promise<Token>;
  validate(token: string): Promise<ValidationResult>;
  revoke(tokenId: string): Promise<void>;
}
```

## Behavioral Contract
- generate() MUST create a JWT with HS256 signing
- generate() MUST set expiry to 24 hours from creation
- validate() MUST return {valid: false, error: "expired"} for expired tokens
- validate() MUST NOT throw exceptions, always return a result object
- revoke() MUST be idempotent (revoking a non-existent token returns success)

## Edge Cases to Handle
- Empty scopes array → default to ["read"]
- userId longer than 128 chars → throw ValidationError
- Token string that isn't valid JWT → return {valid: false, error: "malformed"}

## Unit Tests (pre-written by Architect)
[Opus writes the tests. Grok's job is to make them pass.]

## Constraints
- Use jsonwebtoken library (already in package.json)
- No database calls — token storage is in-memory Map for now
- Must be async-compatible for future DB migration
```

### 6.2 The Workflow Loop

```
Step 1: You → L4 (Opus): "Design the auth token system for [project].
        Output a spec using the Implementation Spec format."

Step 2: Opus outputs the spec (expensive, but one-time)

Step 3: You → L3 (Grok): "Implement this spec exactly. Make all tests pass."
        [Paste the spec as context]

Step 4: Grok implements (cheap, may take 2-3 iterations)

Step 5: Run tests locally. If failures:
        - Simple failures → back to L3 (Grok fixes for cheap)
        - If Grok fails same issue 2-3 times → escalate to L4 with the error

Step 6: You → L4 (Opus): "Review this implementation against the spec.
        Flag any deviations, security issues, or missed edge cases."
        [Paste implementation as context]
```

**Cost estimate for a typical feature:**
- L4 spec generation: ~2K output tokens = ~$0.05
- L3 implementation (3 iterations): ~30K tokens = ~$0.006
- L4 review: ~2K output tokens = ~$0.05
- **Total: ~$0.11 per feature** vs $2+ if you used Opus for everything

---

## Part 7: Budget Safety Rails

### 7.1 Add PostgreSQL (for persistent budget tracking)

Update your `C:\litellm-proxy\docker-compose.yml`:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: litellm
      POSTGRES_PASSWORD: litellm_password
      POSTGRES_DB: litellm_db
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U litellm"]
      interval: 10s
      timeout: 5s
      retries: 5

  litellm:
    image: litellm/litellm:main-latest
    depends_on:
      postgres:
        condition: service_healthy
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql://litellm:litellm_password@postgres:5432/litellm_db
    volumes:
      - ./config.yaml:/app/config.yaml
    ports:
      - "4000:4000"
    command: ["--config", "/app/config.yaml", "--port", "4000"]
    dns:
      - 8.8.8.8
      - 1.1.1.1
    restart: unless-stopped

volumes:
  postgres_data:
```

### 7.2 Create Budget-Limited API Keys

Once PostgreSQL is running, create separate keys for different uses:

```powershell
$MASTER_KEY = "sk-litellm-master-change-this-to-something-random"

# Key for Cursor (daily coding, $5/day limit)
curl http://localhost:4000/key/generate -H "Authorization: Bearer $MASTER_KEY" -H "Content-Type: application/json" -d '{\"max_budget\": 5, \"budget_duration\": \"1d\", \"key_alias\": \"cursor-daily\", \"models\": [\"l1-intern\", \"l2-junior\", \"l3-senior\", \"default\"]}'

# Key for architecture work (higher limit, includes L4)
curl http://localhost:4000/key/generate -H "Authorization: Bearer $MASTER_KEY" -H "Content-Type: application/json" -d '{\"max_budget\": 20, \"budget_duration\": \"7d\", \"key_alias\": \"architect-weekly\", \"models\": [\"l3-senior\", \"l4-architect\", \"l3-sonnet\"]}'

# Key for the Oracle script ($2/day, safety net for runaway loops)
curl http://localhost:4000/key/generate -H "Authorization: Bearer $MASTER_KEY" -H "Content-Type: application/json" -d '{\"max_budget\": 2, \"budget_duration\": \"1d\", \"key_alias\": \"oracle-daily\"}'
```

### 7.3 Monitor Spend

```powershell
# Check spend on a key
curl http://localhost:4000/key/info -H "Authorization: Bearer sk-your-generated-key"

# LiteLLM dashboard (if enabled):
# http://localhost:4000/ui
```

---

## Part 8: Quick Reference

### Start Everything

```powershell
# 1. Ollama starts automatically with Windows (system tray)
#    If not running, launch from Start Menu

# 2. Pre-load the Intern model
ollama run qwen2.5:1.5b --keepalive -1
# Type /bye to exit chat (model stays loaded)

# 3. Start LiteLLM proxy
cd C:\litellm-proxy
docker compose up -d

# 4. Open Cursor, start coding
```

### Stop Everything

```powershell
cd C:\litellm-proxy
docker compose down

# Ollama: right-click tray icon → Quit
# Or: ollama stop qwen2.5:1.5b && ollama stop qwen2.5-coder:7b
```

### Model Quick Reference

| When to use | Model name in Cursor/API |
|-------------|--------------------------|
| "What does this file do?" | `l1-intern` |
| "Write a test for this function" | `l2-junior` |
| "Fix this bug" / "Implement this feature" | `l3-senior` |
| "Design the system" / "Review architecture" | `l4-architect` |
| Not sure | `default` (routes to L3) |

### Escalation Rules

1. **L1 fails** → auto-retry once → escalate to L3 (skip L2 for speed)
2. **L2 fails twice** → escalate to L3
3. **L3 fails 2-3 times on same issue** → manually escalate to L4
4. **Context >3 files or >8K tokens** → skip local, go straight to L3

### Estimated Daily Costs

| Usage Pattern | L1/L2 (free) | L3 (Grok) | L4 (Opus) | Total |
|---------------|--------------|-----------|-----------|-------|
| Light day | 80% | 18% | 2% | ~$0.10 |
| Normal day | 60% | 35% | 5% | ~$0.50 |
| Heavy architecture day | 30% | 40% | 30% | ~$5.00 |

---

## Appendix A: Troubleshooting (Windows)

### Ollama not reachable from LiteLLM Docker container

```powershell
# Verify Ollama is listening on all interfaces
curl http://localhost:11434/api/tags

# Check OLLAMA_HOST is set to 0.0.0.0:11434
# (see Part 2.2 for environment variable setup)
# Restart Ollama after changing env vars
```

### Docker can't pull images

```powershell
# Check Docker Desktop is running (system tray icon)
# If DNS issues, try in Docker Desktop: Settings → Docker Engine → add:
# "dns": ["8.8.8.8", "1.1.1.1"]
```

### curl JSON escaping issues in PowerShell

PowerShell is notorious for mangling JSON. Options:

```powershell
# Option 1: Use cmd.exe instead of PowerShell for curl commands
cmd /c 'curl http://localhost:4000/models -H "Authorization: Bearer sk-your-key"'

# Option 2: Use Python instead
python -c "import requests; print(requests.get('http://localhost:4000/models', headers={'Authorization': 'Bearer sk-your-key'}).json())"

# Option 3: Use Invoke-RestMethod (native PowerShell)
$headers = @{ "Authorization" = "Bearer sk-your-key" }
Invoke-RestMethod -Uri "http://localhost:4000/models" -Headers $headers
```

### LiteLLM can't find models

```powershell
# Check config is mounted correctly
docker exec litellm-proxy-litellm-1 cat /app/config.yaml

# Check logs
docker logs litellm-proxy-litellm-1 --tail 50
```

### Windows Firewall blocking connections

If Cursor or other tools can't reach `localhost:4000`:

```powershell
# Run PowerShell as Administrator
New-NetFirewallRule -DisplayName "LiteLLM Proxy" -Direction Inbound -Port 4000 -Protocol TCP -Action Allow
New-NetFirewallRule -DisplayName "Ollama" -Direction Inbound -Port 11434 -Protocol TCP -Action Allow
```

---

## Appendix B: Adding PostgreSQL Later

If you started without PostgreSQL and want to add budget tracking:

1. Update `docker-compose.yml` with the PostgreSQL version from Part 7.1
2. Add `DATABASE_URL` to your `.env` file: `DATABASE_URL=postgresql://litellm:litellm_password@postgres:5432/litellm_db`
3. Restart: `docker compose down && docker compose up -d`
4. Generate API keys as shown in Part 7.2

Your existing config.yaml doesn't need changes — the database is for key/budget management only.

---

## Appendix C: Phase 2 Roadmap — UiPath Assistant Integration

The Phase 2 goal is to inject an AI terminal into UiPath Assistant, using the 4-level model to determine how to build and route RPA projects.

### Why Native Windows Matters

UiPath Assistant runs as a Windows desktop application. Your AI agent needs to:
- Read/write `.xaml` files directly on the Windows filesystem
- Execute UiPath CLI commands (`uipcli`) natively
- Interact with UiPath Orchestrator APIs
- Potentially use computer-use models to interact with UiPath Studio

All of these require direct Windows access — which is why the entire stack in this guide runs natively, not in WSL2.

### Conceptual Architecture

```
┌─────────────────────────────────────────────┐
│              UiPath Assistant                │
│  ┌───────────────────────────────────────┐  │
│  │         AI Terminal (injected)        │  │
│  │                                       │  │
│  │  User prompt → Oracle → Route to:     │  │
│  │    L1: Run UiPath CLI commands        │  │
│  │    L2: Generate simple .xaml snippets  │  │
│  │    L3: Build full RPA workflows       │  │
│  │    L4: Design RPA architecture        │  │
│  └──────────────┬────────────────────────┘  │
│                 │                            │
└─────────────────┼────────────────────────────┘
                  │
        ┌─────────▼──────────┐
        │   LiteLLM Proxy    │
        │  localhost:4000     │
        │                    │
        │  L1 ──→ Ollama     │
        │  L2 ──→ Ollama     │
        │  L3 ──→ Grok API   │
        │  L4 ──→ Opus API   │
        └────────────────────┘
```

### Phase 2 Tasks (to be designed later)

- Build the AI terminal UI component for UiPath Assistant
- Extend the Oracle with UiPath-specific routing rules (e.g., "create an attended automation" → L3)
- Add `.xaml` generation capabilities to the L3 prompt templates
- Add computer-use model integration for visual UiPath Studio interaction
- Connect to UiPath Orchestrator for deployment and monitoring

This guide gets the foundation right. Phase 2 builds on top of it.

---

## Appendix D: Future Upgrades

**When you get a GPU:**
- Add larger local models (Qwen 32B, DeepSeek-R1 distills)
- L2 becomes much more capable, further reducing cloud costs
- Update `config.yaml` to add new Ollama models

**When you want Aider alongside Cursor:**
```powershell
pip install aider-chat

# Set environment variables
$env:OPENAI_API_BASE = "http://localhost:4000/v1"
$env:OPENAI_API_KEY = "your-litellm-key"

# Use any model from your config
aider --model l3-senior
```

**When you want the Oracle integrated into your tools:**
The Oracle script (Part 4) is a standalone router. Import `classify()` and `route_and_execute()` from `oracle.py` into your custom agent code. The classification logic stays the same.
