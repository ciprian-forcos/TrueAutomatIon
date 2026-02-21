# Phase 1 Task List: UiPath Assistant — Claude Code Terminal Integration

**Objective**: Inject terminal capabilities into UiPath Assistant that support Claude Code execution,
multiple concurrent instances, and configurable/custom model backends.

**Target app**: `C:\Program Files\UiPathPlatform\Studio\26.0.187-cloud.22164\UiPathAssistant\`
**Stack**: Electron (main.js Node.js process) + Angular frontend (shell/) + Chromium renderer
**Constraint**: All source is minified/bundled. No source maps. Work is injection/monkey-patching or
a sidecar approach, not direct source modification.

---

## SECTION 1 — INVESTIGATION TASKS

### TASK INV-01: Deep-parse main.js IPC router
**File**: `resources/app/main.js` (~1.9MB bundled)
**Goal**: Map the exact IPC handler registration pattern so new channels can be injected using
the same mechanism.
**What to do**:
- Search for `ipcMain.handle(` and `ipcMain.on(` call sites in main.js
- Find the function/closure that registers all `/channel/*` routes
- Identify whether channels are registered in a single init block or spread across modules
- Note the exact call signature (sync `ipcMain.on` vs async `ipcMain.handle`)
- Record line numbers and surrounding function names (even in minified form, variable names
  in closures are partially preserved)
**Expected output**: A map of `channel_name → handler_function_ref` with line numbers in main.js

---

### TASK INV-02: Map child_process spawn call sites in main.js
**File**: `resources/app/main.js`
**Goal**: Understand how existing subprocesses are launched so Claude Code instances can follow
the same pattern.
**What to do**:
- Search for all `spawn(`, `exec(`, `fork(`, `execFile(` call sites
- For each, identify: command spawned, args pattern, stdio config (pipe/inherit/ignore),
  error/exit handling, whether stdout is streamed back over IPC
- Identify which spawn calls stream output back to the renderer via IPC channels
- Find the pattern used for long-running vs one-shot processes
**Expected output**: Annotated list of spawn call sites, their purpose, and the streaming pattern
used (if any)

---

### TASK INV-03: Reverse-engineer preload.js context bridge
**File**: `resources/app/preload.js` (~1.8KB, partially readable)
**Goal**: Understand the exact API surface exposed to the Angular renderer so new terminal APIs
can be added in the same style.
**What to do**:
- Read the full file (small enough to parse manually)
- Document every property exposed via `contextBridge.exposeInMainWorld()`
- Document the exact shape of `window.ipcRenderer` (callMain, addListener, removeListener,
  removeAllListeners signatures)
- Note any security restrictions (channel allowlist, origin checks)
- Check if there is a channel allowlist that must be extended to add new channels
**Expected output**: Full documented API surface of the context bridge + any allowlist constraints

---

### TASK INV-04: Locate widget/extension loader in main.js
**File**: `resources/app/main.js`
**Goal**: Understand the dev widget loading path (`UIPATH_ASSISTANT_DEV_WIDGET_PATH` env var)
as a potential injection vector that avoids modifying the main bundle.
**What to do**:
- Search for `UIPATH_ASSISTANT_DEV_WIDGET_PATH` string in main.js
- Trace the code path: how is the path read? What is loaded from it? What format is expected
  (URL? local file path? package.json? index.js?)
- Determine if a dev widget can inject new IPC channels into the main process, or only
  add UI to the renderer
- Check `UIPATH_CLIPBOARD_AI_PATH` and `UIPATH_TASK_CAPTURE_PATH` for comparison — these
  are plugin paths that likely follow the same pattern
**Expected output**: Widget/plugin loading contract (entry point format, what APIs are available
to a plugin, whether main-process code can be injected)

---

### TASK INV-05: Map Named Pipe protocol to UiPath Robot service
**Files**: `resources/app/main.js`, `assets/utils/check-socket-accessible.js`,
           `assets/utils/socket.io-client.js`
**Goal**: Understand the Robot service IPC so we don't accidentally interfere with it when
adding our own IPC channels.
**What to do**:
- Find the Named Pipe connection setup (search for `\\.\pipe\` or `UiPathUserService`)
- Identify message format (JSON-RPC? protobuf? custom?)
- Find reconnection/health-check logic
- Note what happens when the pipe is unavailable (fallback behavior)
**Expected output**: Protocol summary + risk assessment of interference

---

### TASK INV-06: Angular shell route and module structure
**Files**: `resources/app/shell/index.html`, `shell/main-LAJF4F5E.js`,
           `shell/prerendered-routes.json`, all `chunk-*.js` files
**Goal**: Identify where a new "Terminal" or "Claude" tab/panel can be added without breaking
existing navigation.
**What to do**:
- Read `prerendered-routes.json` to get the full route list
- In main bundle, search for the router configuration (Angular `RouterModule.forRoot(`)
- Identify the tab/navigation component (likely in main bundle, search for `TabComponent`
  or nav-related class names)
- Check if routes are lazy-loaded (they appear to be — each chunk is a feature module)
- Identify the lazy-load registration pattern (`loadChildren: () => import(...)`)
**Expected output**: Route map + instructions for how a new lazy-loaded route/module would be
registered

---

### TASK INV-07: Keytar usage pattern for credential storage
**File**: `resources/app/main.js`, `binaries/build/Release/keytar.node`
**Goal**: Understand how to store API keys (Anthropic, custom model endpoints) using the
existing credential mechanism.
**What to do**:
- Search for `keytar` in main.js
- Document: service names used, account names used, which IPC channels expose get/set operations
  to the renderer
- Confirm that keytar is invoked from the main process only (as required — never from renderer)
**Expected output**: keytar usage pattern + IPC channels for credential read/write

---

### TASK INV-08: Settings persistence mechanism
**File**: `resources/app/main.js`
**Goal**: Identify how user settings are stored (electron-store? JSON file? registry?) so
Claude Code config (model selection, API keys, instance limits) can be persisted the same way.
**What to do**:
- Search for `electron-store`, `electron-settings`, `app.getPath('userData')`, `fs.writeFile`
  patterns related to settings
- Find the settings schema/object shape
- Identify IPC channels: `/channel/settings/updated` handler — trace what it reads/writes
**Expected output**: Settings storage mechanism, file path, schema shape

---

## SECTION 2 — INITIAL DESIGN

### TASK DES-01: Architecture decision — Injection approach
**Depends on**: INV-04 (widget loader)
**Goal**: Choose between three injection strategies and document the rationale.

**Option A — Dev Widget Sidecar** (preferred if INV-04 confirms main-process injection is possible)
- Set `UIPATH_ASSISTANT_DEV_WIDGET_PATH` to a local Node.js package we own
- Our package injects new IPC channels from main process on load
- Angular UI component served from our package and loaded into renderer as a widget
- Zero modification to UiPath files — fully external
- Risk: widget API may not allow main-process code injection

**Option B — Patched main.js**
- Append our extension module to the end of main.js
- Our code registers new IPC channels and spawns Claude Code process
- Angular UI injected via a renderer-side script tag added to index.html
- Risk: breaks on UiPath updates, requires re-patching

**Option C — Electron Forge / asar repack**
- Unpack the asar (if present) or work with loose files directly
- Replace main.js and preload.js with patched versions
- Repack
- Risk: code signing may break; harder to maintain

**Deliverable**: ADR (Architecture Decision Record) document selecting approach with justification

---

### TASK DES-02: Terminal UI component design
**Goal**: Design the Angular component that hosts Claude Code terminal sessions.
**Requirements**:
- xterm.js-based terminal emulator (industry standard for Electron terminal UIs)
- Tab bar for multiple instances (each tab = one `claude` process)
- Instance controls: new session, kill session, rename session
- Status indicator per instance (idle / running / error)
- Model selector dropdown (Anthropic API / custom OpenAI-compatible endpoint)
- Settings panel: API key input (writes to keytar via IPC), base URL override, model name
- Persistent session history per instance (ring buffer, configurable size)
- Theme: inherit UiPath Apollo design tokens (dark/light follows Assistant theme)
**Deliverable**: Component tree diagram + data flow diagram (IPC ↔ Angular ↔ xterm.js)

---

### TASK DES-03: IPC channel contract definition
**Goal**: Define the full IPC API between Angular renderer and Node.js main process.
**Channels to define**:
```
/channel/claude/start-session
  Request:  { instanceId: string, model: string, cwd: string }
  Response: { instanceId: string, pid: number }

/channel/claude/kill-session
  Request:  { instanceId: string }
  Response: { success: boolean }

/channel/claude/list-sessions
  Request:  {}
  Response: { sessions: Array<{ instanceId, pid, model, cwd, status }> }

/channel/claude/stdin
  Request:  { instanceId: string, data: string }
  Response: void (fire-and-forget)

/channel/claude/stdout  (main → renderer, event)
  Payload:  { instanceId: string, data: string }

/channel/claude/exit   (main → renderer, event)
  Payload:  { instanceId: string, code: number }

/channel/claude/save-config
  Request:  { apiKey?: string, baseUrl?: string, model?: string }
  Response: { success: boolean }

/channel/claude/load-config
  Request:  {}
  Response: { baseUrl: string, model: string, hasApiKey: boolean }
```
**Deliverable**: TypeScript interface definitions file for all channel payloads

---

### TASK DES-04: Process manager design
**Goal**: Design the Node.js process manager that runs in the Electron main process.
**Requirements**:
- Spawn `claude` CLI or Node.js Claude SDK process per instance
- Support custom `ANTHROPIC_BASE_URL` env var for custom model endpoints
- Support `ANTHROPIC_API_KEY` from keytar (never from renderer)
- PTY (pseudo-terminal) support via `node-pty` for proper terminal emulation
  (raw spawn gives no color, no readline — xterm.js needs a PTY)
- Stream stdout/stderr to renderer via `/channel/claude/stdout` IPC events
- Write stdin from renderer to PTY
- Track instance state machine: `starting → ready → running → idle → terminated`
- Max instance limit (configurable, default 5)
- Cleanup on app quit: SIGTERM all managed processes
**Deliverable**: Class diagram for ProcessManager + InstanceState machine diagram

---

## SECTION 3 — IMPLEMENTATION REQUIREMENTS

### TASK REQ-01: Dependency audit and acquisition
**Goal**: Identify all new npm packages required and assess compatibility with existing Electron version.
**Packages needed**:
- `node-pty`: Native PTY module — **must match Electron ABI** — requires rebuild with
  `electron-rebuild` against the exact Electron version in the Assistant binary
  (determine version from `process.versions.electron` in DevTools or from Electron binary metadata)
- `xterm`: Terminal emulator for Angular renderer (renderer-side, no native dependency)
- `xterm-addon-fit`: Auto-resize xterm to container
- `xterm-addon-web-links`: Clickable links in terminal output
- `@anthropic-ai/sdk` (optional — if calling API directly rather than spawning `claude` CLI)

**Electron version detection**:
- Open DevTools in Assistant (if possible) and run `process.versions.electron`
- Or: check the Electron binary version by examining `UiPath.Assistant.exe` PE headers or
  running `UiPath.Assistant.exe --version`

**Deliverable**: Package list with exact versions, ABI compatibility matrix, rebuild instructions

---

### TASK REQ-02: node-pty build requirements
**Goal**: node-pty is a native module that must be compiled against the exact Electron ABI.
**Steps**:
- Identify Electron version (from REQ-01)
- Set up build environment: Python 3.x, MSVC Build Tools (Visual Studio Build Tools 2019+),
  windows-build-tools
- Run: `npm install node-pty` then `npx electron-rebuild -f -w node-pty -v <electron-version>`
- Verify: produced `.node` file loads without error in matching Electron version
- Note: UiPath ships with `keytar.node` as precedent — same process applies here
**Deliverable**: Build script + verification test

---

### TASK REQ-03: Claude CLI / SDK invocation contract
**Goal**: Define exactly how Claude Code is invoked — CLI subprocess vs SDK.
**Option A — CLI subprocess** (simpler, no API key in Node.js memory):
- Requires `claude` CLI installed and on PATH, or full path provided in config
- Spawn: `spawn('claude', ['--model', model, ...flags], { env: { ANTHROPIC_API_KEY: key } })`
- PTY wraps this spawn

**Option B — Anthropic Node.js SDK** (more control, streaming built-in):
- Import `@anthropic-ai/sdk` in main process
- Stream responses back over IPC
- API key loaded from keytar, never touches renderer

**Deliverable**: Decision + invocation wrapper implementation spec

---

### TASK REQ-04: Custom model endpoint requirements
**Goal**: Define what "custom model" means and what config is needed.
**Supported backends**:
1. Anthropic API (default) — `ANTHROPIC_API_KEY` + `https://api.anthropic.com`
2. OpenAI-compatible endpoint — `base_url` + `api_key` + `model_name`
   (e.g., Azure OpenAI, OpenRouter, local Ollama with OpenAI-compat layer,
   LiteLLM proxy — which is already present in this repo's docker-compose)
3. LiteLLM proxy (internal) — base URL points to local LiteLLM instance

**Config schema**:
```json
{
  "profiles": [
    {
      "name": "Anthropic (default)",
      "baseUrl": "https://api.anthropic.com",
      "model": "claude-sonnet-4-6",
      "apiKeyKeytarService": "UiPathAssistantClaudeCode",
      "apiKeyKeytarAccount": "anthropic-default"
    },
    {
      "name": "LiteLLM Local",
      "baseUrl": "http://localhost:4000",
      "model": "grok-3",
      "apiKeyKeytarService": "UiPathAssistantClaudeCode",
      "apiKeyKeytarAccount": "litellm-local"
    }
  ],
  "activeProfile": "Anthropic (default)",
  "maxInstances": 5
}
```
**Deliverable**: Full config schema (JSON Schema format) + validation logic spec

---

### TASK REQ-05: Security requirements
**Goal**: Ensure the terminal integration doesn't introduce privilege escalation or key leakage.
**Requirements**:
- API keys stored exclusively in Windows Credential Manager via keytar — never in plain files,
  never sent to renderer process, never logged
- `claude` subprocess inherits only explicitly whitelisted env vars (no full process env passthrough)
- Terminal cwd defaulted to user home or configurable safe path — not system directories
- IPC channel allowlist in preload.js must be extended with `/channel/claude/*` channels only —
  no wildcard expansion
- PTY output sanitized before IPC transmission (strip ANSI where appropriate, or pass raw
  and let xterm.js handle it — prefer raw for proper rendering)
- Instance kill must SIGTERM then SIGKILL with timeout — no zombie processes
**Deliverable**: Security checklist + threat model (one-pager)

---

## SECTION 4 — IMPLEMENTATION PLAN

### TASK IMP-01: Bootstrap the extension package
**Depends on**: DES-01 (architecture decision), REQ-01
**Steps**:
1. Create `C:\Users\<user>\AppData\Local\UiPathAssistantExtensions\claude-terminal\` directory
2. Initialize `package.json` with `"main": "index.js"`
3. Create stub `index.js` that logs on load: `console.log('[claude-terminal] loaded')`
4. Set env var `UIPATH_ASSISTANT_DEV_WIDGET_PATH` to the package directory
5. Launch Assistant and verify stub loads (check DevTools console or Assistant logs)
6. If stub loads in renderer only (not main process): reassess — may need Option B/C from DES-01
**Deliverable**: Working stub extension that loads on Assistant startup

---

### TASK IMP-02: Implement ProcessManager in main process
**Depends on**: DES-04, REQ-02, REQ-03
**File**: `claude-terminal/src/process-manager.js`
**Steps**:
1. Require `node-pty`
2. Implement `ProcessManager` class:
   ```
   class ProcessManager {
     constructor(keytarRef)
     async startSession(instanceId, { model, baseUrl, cwd }) → { pid }
     killSession(instanceId)
     writeStdin(instanceId, data)
     listSessions() → Array<SessionInfo>
     destroyAll()  // called on app 'before-quit'
   }
   ```
3. On `startSession`: retrieve API key from keytar, spawn PTY with correct env, attach
   stdout listener that emits IPC event `/channel/claude/stdout` to sender window
4. On `killSession`: send SIGTERM, wait 3s, send SIGKILL if still running
5. Attach to Electron `app.on('before-quit')` to call `destroyAll()`
**Deliverable**: Tested ProcessManager module (unit test with mock PTY)

---

### TASK IMP-03: Register IPC channels in main process
**Depends on**: IMP-01 (extension loads in main process), DES-03, IMP-02
**File**: `claude-terminal/src/ipc-handlers.js`
**Steps**:
1. Import `ipcMain` from electron (available in main process context)
2. Import `ProcessManager`
3. Register all channels from DES-03 using `ipcMain.handle()` for request/response,
   `ipcMain.on()` for fire-and-forget (stdin)
4. For stdout push events: in ProcessManager, capture the `sender` webContents reference
   from the `start-session` call and emit back to it via `sender.send('/channel/claude/stdout', ...)`
5. Extend preload.js allowlist: if there is a channel allowlist array, add `/channel/claude/` prefix.
   If preload.js is too restrictive, patch it (Option B) or confirm dev widget bypasses it.
**Deliverable**: All IPC channels registered and testable via DevTools `window.ipcRenderer.callMain()`

---

### TASK IMP-04: Implement Angular terminal component
**Depends on**: DES-02, IMP-03 (IPC channels working)
**File**: `claude-terminal/src/renderer/terminal.component.ts` (TypeScript + Angular)
**Steps**:
1. Create Angular standalone component (no NgModule needed for injection approach)
2. Import xterm.js `Terminal` and addons
3. Component inputs: `instanceId: string`
4. On init: create xterm Terminal, call `fit()`, attach to container div
5. Subscribe to `window.ipcRenderer.addListener('/channel/claude/stdout', ...)` → write to terminal
6. On keydown in terminal: call `window.ipcRenderer.callMain('/channel/claude/stdin', { instanceId, data })`
7. On destroy: call `window.ipcRenderer.callMain('/channel/claude/kill-session', { instanceId })`
   and remove IPC listener
**Deliverable**: Working terminal component that connects to a real `claude` process

---

### TASK IMP-05: Implement instance tab manager component
**Depends on**: IMP-04
**File**: `claude-terminal/src/renderer/tab-manager.component.ts`
**Steps**:
1. State: `sessions: Array<{ instanceId, label, status }>`
2. "New Session" button: calls `/channel/claude/start-session`, generates UUID instanceId,
   adds to sessions array, switches active tab
3. Tab bar: click switches active terminal component
4. Close button per tab: calls `/channel/claude/kill-session`, removes from array
5. On init: call `/channel/claude/list-sessions` and restore any existing sessions
   (survives renderer reload)
6. Session limit enforcement: disable "New Session" when `sessions.length >= maxInstances`
**Deliverable**: Multi-tab terminal UI working end-to-end

---

### TASK IMP-06: Implement settings/config panel
**Depends on**: IMP-05, REQ-04
**File**: `claude-terminal/src/renderer/settings.component.ts`
**Steps**:
1. Load config on open: call `/channel/claude/load-config`
2. Profile list: display profiles from config, allow selecting active profile
3. Add/edit profile form: name, baseUrl, model, API key (password input, write-only display)
4. Save: call `/channel/claude/save-config` — API key goes to keytar via main process
5. Test connection button: start a minimal session with a `claude --version` invocation and
   show success/failure
6. Style: follow Apollo design tokens (CSS variables already in shell for dark/light theme)
**Deliverable**: Working settings panel with profile management

---

### TASK IMP-07: Inject terminal UI into Assistant shell
**Depends on**: IMP-05, IMP-06, DES-01 (architecture decision)
**Goal**: Make the terminal UI appear inside the Assistant window.

**If dev widget approach (Option A)**:
1. Register widget manifest pointing to our Angular component bundle
2. Assistant loads widget as a panel/tab using its widget host mechanism
3. Widget receives same theme/context as other widgets

**If main.js patch (Option B)**:
1. Add `<script>` tag to `shell/index.html` pointing to our bundle
2. Our bootstrap script: waits for Angular to finish bootstrapping (watch for `app-root` to be
   populated), then dynamically adds a new route + nav item using Angular's runtime router
3. This requires finding the Angular app's `Router` instance in the global injector:
   `(window as any).ng.getInjector(document.querySelector('app-root')).get(Router)`
**Deliverable**: Terminal accessible from Assistant UI navigation

---

### TASK IMP-08: Integration testing
**Steps**:
1. Launch Assistant with extension active
2. Verify: new terminal tab/panel visible
3. Verify: start new Claude Code session → process spawns, terminal connects
4. Verify: type input → appears in terminal → Claude responds
5. Verify: open 3 sessions simultaneously → all independent
6. Verify: switch models via settings → new session uses new model
7. Verify: kill session → process terminates, tab closes cleanly
8. Verify: close Assistant → all claude processes terminated (no orphans in Task Manager)
9. Verify: Assistant update (version bump) → extension still loads (or documents what breaks)
**Deliverable**: Test results document + list of known issues

---

## APPENDIX: KEY FILE REFERENCE

| File | Path | Notes |
|------|------|-------|
| Main process entry | `resources/app/main.js` | 1.9MB minified, Webpack bundle |
| Context bridge | `resources/app/preload.js` | ~1.8KB, partially readable |
| Angular entry | `resources/app/shell/index.html` | Bootstrap point for renderer |
| Angular main bundle | `resources/app/shell/main-LAJF4F5E.js` | Hash changes per build |
| Route manifest | `resources/app/shell/prerendered-routes.json` | Angular routes |
| Credential module | `resources/app/binaries/build/Release/keytar.node` | Native PE32+ x64 |
| Socket util | `resources/app/assets/utils/socket.io-client.js` | WebSocket client |
| Window actions | `resources/app/assets/utils/add-window-actions.js` | Window management |

## APPENDIX: ENVIRONMENT VARIABLES

| Variable | Purpose |
|----------|---------|
| `UIPATH_ASSISTANT_DEV_WIDGET_PATH` | Path to dev widget package (primary injection vector) |
| `UIPATH_CLIPBOARD_AI_PATH` | Clipboard AI plugin path (reference implementation) |
| `UIPATH_TASK_CAPTURE_PATH` | Task capture plugin path (reference implementation) |
| `UIPATH_ASSISTANT_EXTENSION_LOGGING` | Enable extension debug logging |
| `UIPATH_USER_SERVICE_PATH` | Robot service path (do not interfere) |

## APPENDIX: IPC CHANNELS (EXISTING — DO NOT CONFLICT)

All existing channels use prefix `/channel/robot/`, `/channel/settings/`, `/channel/shell/`,
`/channel/widgets/`, `/channel/notifications/`, `/channel/forms/`.
Our new channels use `/channel/claude/` — no conflicts.
