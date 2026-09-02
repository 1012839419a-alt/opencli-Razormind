# CloakBrowser Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in CloakBrowser executable to the existing Chrome and embedded-agent containers without changing the CDP, Bridge, profile, or browser-pool contracts.

**Architecture:** Build-time `BROWSER_ENGINE=cloakbrowser` installs the official Node wrapper and warms its signed binary cache. A shared resolver script selects the stock Chromium executable or invokes the official `ensureBinary()` at container start. Both entrypoints keep the existing CDP ports, runtime bundle, persistent profile, and fail-closed readiness behavior.

**Tech Stack:** Debian slim, Node.js 22, npm, Bash entrypoints, Docker Compose, Python/pytest source-contract tests, Chromium CDP.

**Spec:** `docs/superpowers/specs/2026-09-02-cloakbrowser-compatibility-design.md`

## Global Constraints

- Default `BROWSER_ENGINE` remains `chromium`.
- Supported values are exactly `chromium` and `cloakbrowser`; unknown values fail closed.
- `CLOAKBROWSER_LICENSE_KEY` is runtime-only and must not be logged, persisted, or baked into an image.
- CloakBrowser resolution/download/signature/license/cache failures never fall back to stock Chromium.
- Existing CDP ports (`9222` internal, `19222` through nginx), Bridge daemon, runtime bundle, startup pages, network policy, and profile paths remain unchanged.
- Do not change `backend/browser_pool.py`, `OpenCLIChannel`, database models, or browser transport protocols.
- Do not run formatters, linters, or project-wide test suites in individual tasks; run focused checks at the end.

## File Map

- `scripts/resolve-browser-executable.mjs`: shared engine validation and executable resolution; no secret output.
- `chrome/Dockerfile`: opt-in CloakBrowser npm package/cache installation and resolver packaging.
- `chrome/entrypoint.sh`: resolve selected executable before the existing `start_chrome()` loop.
- `agent/Dockerfile`: same opt-in package/cache support for embedded remote agents.
- `agent/entrypoint.sh`: select the resolved executable for embedded Chrome while preserving host-Chrome mode.
- `docker-compose.build.yml`: pass engine/version build args to the Chrome and embedded-agent images.
- `docker-compose.yml`: expose non-secret engine/cache/version settings and optional runtime license key to the built-in browser service.
- `.env.example` and `.env.docker.example`: document opt-in build/run configuration and security limitations.

### Task 1: Add the shared executable resolver

**Files:**
- Create: `scripts/resolve-browser-executable.mjs`
- Test: `tests/unit/test_browser_executable.py`

**Interfaces:**
- CLI: `node scripts/resolve-browser-executable.mjs <engine>`
- Inputs: `BROWSER_ENGINE`, `CLOAKBROWSER_BINARY_PATH`, `CLOAKBROWSER_CACHE_DIR`, and the installed `/opt/cloakbrowser` Node package.
- Output: exactly one executable path on stdout; diagnostics only on stderr and never include license values.
- Failure: non-zero exit for unknown engine, missing override, missing wrapper, or `ensureBinary()` failure.

- [ ] **Step 1: Write failing tests**

```python
def test_resolver_accepts_stock_chromium():
    result = run_resolver("chromium")
    assert result.stdout.strip() == "chromium"


def test_resolver_uses_existing_cloak_binary(tmp_path):
    binary = tmp_path / "cloak"
    binary.write_bytes(b"binary")
    result = run_resolver("cloakbrowser", {"CLOAKBROWSER_BINARY_PATH": str(binary)})
    assert result.stdout.strip() == str(binary)


def test_resolver_rejects_unknown_engine():
    result = run_resolver("webkit")
    assert result.returncode != 0
    assert "webkit" in result.stderr


def test_resolver_does_not_fallback_when_override_missing(tmp_path):
    result = run_resolver(
        "cloakbrowser",
        {"CLOAKBROWSER_BINARY_PATH": str(tmp_path / "missing")},
    )
    assert result.returncode != 0
    assert "fallback" not in result.stderr.lower()
```

Use `subprocess.run(["node", str(ROOT / "scripts/resolve-browser-executable.mjs"), engine], env=..., capture_output=True, text=True)` and preserve the host environment except for test overrides.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `pytest tests/unit/test_browser_executable.py -q`
Expected: FAIL because the resolver does not exist.

- [ ] **Step 3: Implement the resolver**

Implement explicit engine branching. For `chromium`, print `process.env.CHROMIUM_BINARY || "chromium"`. For `cloakbrowser`, validate a non-empty `CLOAKBROWSER_BINARY_PATH` with `fs.existsSync()` and print it; otherwise import `ensureBinary` from `/opt/cloakbrowser` and print `await ensureBinary()`. Wrap only the public error message with `CloakBrowser executable resolution failed`; never print `process.env.CLOAKBROWSER_LICENSE_KEY` or arbitrary exception text that might contain it. Reject all other engines before touching the filesystem.

- [ ] **Step 4: Run focused tests and verify success**

Run: `pytest tests/unit/test_browser_executable.py -q`
Expected: PASS for stock, override, unknown-engine, and no-fallback cases.

### Task 2: Package CloakBrowser into selectable Docker images

**Files:**
- Modify: `chrome/Dockerfile`
- Modify: `agent/Dockerfile`
- Modify: `docker-compose.build.yml`
- Test: `tests/unit/test_agent_image_runtime_packaging.py`

**Interfaces:**
- Build args: `BROWSER_ENGINE=chromium|cloakbrowser`, `CLOAKBROWSER_VERSION=0.5.10`.
- Runtime env: `BROWSER_ENGINE`, `CLOAKBROWSER_CACHE_DIR=/opt/cloakbrowser/cache`, optional `CLOAKBROWSER_BINARY_PATH` and `CLOAKBROWSER_LICENSE_KEY`.
- Produces: `/usr/local/bin/resolve-browser-executable.mjs`, and when built with CloakBrowser, `/opt/cloakbrowser/node_modules/cloakbrowser` plus a writable signed binary cache.

- [ ] **Step 1: Add source-contract tests**

Extend the existing Dockerfile contract test with assertions that both browser-capable Dockerfiles declare `ARG BROWSER_ENGINE=chromium`, `ARG CLOAKBROWSER_VERSION=0.5.10`, copy the resolver, and conditionally install `cloakbrowser` with `playwright-core`. Assert the build override passes both args to the Chrome and agent image definitions.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `pytest tests/unit/test_agent_image_runtime_packaging.py -q`
Expected: FAIL for the new CloakBrowser assertions.

- [ ] **Step 3: Implement Docker build wiring**

In each Dockerfile, install the package only when `BROWSER_ENGINE=cloakbrowser`:

```dockerfile
ARG BROWSER_ENGINE=chromium
ARG CLOAKBROWSER_VERSION=0.5.10
RUN if [ "$BROWSER_ENGINE" = "cloakbrowser" ]; then \
      mkdir -p /opt/cloakbrowser \
      && npm install --prefix /opt/cloakbrowser --omit=dev \
           "cloakbrowser@${CLOAKBROWSER_VERSION}" "playwright-core@^1.53.0" \
      && CLOAKBROWSER_CACHE_DIR=/opt/cloakbrowser/cache \
           node --input-type=module -e \
           'import {ensureBinary} from "/opt/cloakbrowser/node_modules/cloakbrowser"; await ensureBinary();' \
      ; \
    elif [ "$BROWSER_ENGINE" != "chromium" ]; then \
      echo "Unsupported BROWSER_ENGINE: $BROWSER_ENGINE" >&2; exit 1; \
    fi
```

Copy the resolver after the project source is available. Persist only non-secret defaults with `ENV BROWSER_ENGINE=${BROWSER_ENGINE} CLOAKBROWSER_CACHE_DIR=/opt/cloakbrowser/cache`, create/chown `/opt/cloakbrowser` for the runtime user, and do not add any license `ARG` or `ENV` to the image. In `docker-compose.build.yml`, pass `${BROWSER_ENGINE:-chromium}` and `${CLOAKBROWSER_VERSION:-0.5.10}` to both `x-chrome-build` and `x-agent-build`.

- [ ] **Step 4: Run focused tests and verify success**

Run: `pytest tests/unit/test_agent_image_runtime_packaging.py -q`
Expected: PASS.

### Task 3: Switch both entrypoints without changing lifecycle

**Files:**
- Modify: `chrome/entrypoint.sh`
- Modify: `agent/entrypoint.sh`
- Test: `tests/unit/test_browser_executable.py`

**Interfaces:**
- Both scripts invoke `node /usr/local/bin/resolve-browser-executable.mjs "${BROWSER_ENGINE:-chromium}"`.
- `chrome/entrypoint.sh` assigns the result to `CHROME_BIN` and uses it in `start_chrome()`.
- `agent/entrypoint.sh` resolves only for embedded Chrome and uses it in its existing `start_chrome()` function.

- [ ] **Step 1: Add entrypoint source-contract tests**

Assert both entrypoints call the shared resolver, use `CHROME_BIN` rather than a hard-coded `chromium` command, preserve `--remote-debugging-port=9222`, and contain no `CLOAKBROWSER_LICENSE_KEY` interpolation in log statements.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `pytest tests/unit/test_browser_executable.py -q`
Expected: FAIL for the new entrypoint assertions.

- [ ] **Step 3: Implement executable selection**

In `chrome/entrypoint.sh`, after runtime bundle/startup-page parsing and before `start_chrome()`, add:

```bash
BROWSER_ENGINE="${BROWSER_ENGINE:-chromium}"
CHROME_BIN="$(node /usr/local/bin/resolve-browser-executable.mjs "$BROWSER_ENGINE")" || {
  echo "[entrypoint] Browser engine resolution failed for $BROWSER_ENGINE" >&2
  exit 1
}
echo "[entrypoint] Browser engine: $BROWSER_ENGINE"
```

Replace only the command name in `start_chrome()` with `"$CHROME_BIN"`; leave flags, profile, daemon, nginx, self-check, and restart loop unchanged. Apply the same logic to the embedded branch of `agent/entrypoint.sh`, gated by `AGENT_HAS_CHROME=true`; keep host-Chrome mode untouched. Do not echo the binary path when it can reveal a private mount path.

- [ ] **Step 4: Run focused tests and verify success**

Run: `pytest tests/unit/test_browser_executable.py -q`
Expected: PASS.

### Task 4: Wire Compose configuration and operator documentation

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `.env.docker.example`
- Modify: `README.md`
- Test: `tests/unit/test_browser_docker_config.py`

**Interfaces:**
- `BROWSER_ENGINE` is the runtime selection and must match the image variant.
- `CLOAKBROWSER_VERSION` is a build-time pin.
- `CLOAKBROWSER_LICENSE_KEY` is optional runtime-only secret for the built-in browser service.

- [ ] **Step 1: Add configuration contract tests**

Create `tests/unit/test_browser_docker_config.py` with tests that read the files as UTF-8 and assert:

```python
def test_build_override_passes_engine_and_version_to_browser_images():
    compose = (ROOT / "docker-compose.build.yml").read_text(encoding="utf-8")
    assert "BROWSER_ENGINE: ${BROWSER_ENGINE:-chromium}" in compose
    assert "CLOAKBROWSER_VERSION: ${CLOAKBROWSER_VERSION:-0.5.10}" in compose
    assert compose.count("BROWSER_ENGINE") >= 2


def test_builtin_browser_passes_runtime_engine_without_baking_license():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "BROWSER_ENGINE: ${BROWSER_ENGINE:-chromium}" in compose
    assert "CLOAKBROWSER_CACHE_DIR:" in compose
    assert "CLOAKBROWSER_LICENSE_KEY: ${CLOAKBROWSER_LICENSE_KEY:-}" in compose


def test_env_docs_keep_cloakbrowser_opt_in_and_fail_closed():
    for name in (".env.example", ".env.docker.example"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "BROWSER_ENGINE=chromium" in text
        assert "CLOAKBROWSER_VERSION=0.5.10" in text
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "CloakBrowser" in readme
    assert "不自动降级" in readme
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `pytest tests/unit/test_browser_docker_config.py -q`
Expected: FAIL because the Compose and documentation contracts are not yet present.

- [ ] **Step 3: Implement Compose and docs changes**

Add only non-secret defaults to `.env.example` and `.env.docker.example`:

```dotenv
# Browser engine: chromium (default) or cloakbrowser (requires matching image build)
BROWSER_ENGINE=chromium
CLOAKBROWSER_VERSION=0.5.10
CLOAKBROWSER_CACHE_DIR=/opt/cloakbrowser/cache
# Optional runtime secret; never commit a real value.
# CLOAKBROWSER_LICENSE_KEY=
```

Pass the engine/cache variables through the `agent-1` service and the build args through `docker-compose.build.yml`. Pass the optional license key only as a Compose runtime environment value with an empty default. Document the two-step build/run example and the security/license limitations without claiming CAPTCHA solving or universal anti-bot success.

- [ ] **Step 4: Run focused tests and verify success**

Run: `pytest tests/unit/test_browser_docker_config.py -q`
Expected: PASS.


### Task 5: Build and perform CDP smoke verification

**Files:**
- Modify: none unless focused fixes are required.
- Test: changed source-contract tests and live Docker process.

**Interfaces:**
- Stock smoke: `GET http://localhost:9222/json/version` inside the Chrome container and the existing `19222` endpoint from the API network.
- Cloak smoke: build with `BROWSER_ENGINE=cloakbrowser`, start the container, query `/json/version`, `/json/list`, and navigate through a standard CDP client if Playwright is available.

- [ ] **Step 1: Run all focused unit/config tests**

Run: `pytest tests/unit/test_browser_executable.py tests/unit/test_agent_image_runtime_packaging.py -q`
Expected: PASS.

- [ ] **Step 2: Build the default image and smoke test CDP**

Run: `docker compose -f docker-compose.yml -f docker-compose.build.yml build agent-1` with default `BROWSER_ENGINE=chromium`, then start only `agent-1` and query `http://localhost:9222/json/version` from inside the container. Expected: existing Chromium starts and the endpoint returns JSON with `webSocketDebuggerUrl`; no CloakBrowser package is required.

- [ ] **Step 3: Build the opt-in CloakBrowser image and smoke test CDP**

Run the same build with `BROWSER_ENGINE=cloakbrowser` and the pinned `CLOAKBROWSER_VERSION`, then start `agent-1`. Query `/json/version` and `/json/list`; verify runtime self-check writes `/tmp/browser-runtime-report.json`. If network/license policy prevents the official binary download, record the exact blocker and still verify resolver override behavior with `CLOAKBROWSER_BINARY_PATH`; do not mark the CloakBrowser smoke as passed.

- [ ] **Step 4: Review the diff and run the final focused verification**

Inspect only the changed files and run the focused tests again. Verify no license key, placeholder, test skip, fallback, or hard-coded `chromium` invocation remains in the CloakBrowser path.
