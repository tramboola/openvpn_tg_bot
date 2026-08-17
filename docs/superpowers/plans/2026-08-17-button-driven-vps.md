# Button-driven VPS OpenVPN Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one-protocol OpenVPN initialization, button-driven Telegram administration, persistent filename suffix settings, safe profile revocation, and a two-input Ubuntu VPS installer.

**Architecture:** Keep the existing Python bot and Docker command runner. Add focused modules for durable runtime state, public-IP discovery, and Telegram UI helpers; make Docker operations expose structured profile data; let the bot coordinate workflows and persist only non-secret settings.

**Tech Stack:** Python 3.11+, python-telegram-bot 22.x, Docker Engine, Docker Compose, pytest, POSIX shell for Ubuntu installation.

## Global Constraints

- Only one OpenVPN protocol runs: UDP on `1194/udp` or TCP on `443/tcp`.
- Public IPv4 is detected automatically and is never a normal setup question.
- Installation asks only for `BOT_TOKEN` and `ADMIN_TELEGRAM_ID`.
- The profile suffix changes only the `.ovpn` filename.
- Revocation and full PKI deletion require explicit confirmation.
- No real Docker resources are created or deleted by automated tests.

---

### Task 1: Naming, runtime state, and endpoint discovery

**Files:**
- Create: `src/ovpn_bot/state.py`
- Create: `src/ovpn_bot/public_ip.py`
- Modify: `src/ovpn_bot/docker_logic.py`
- Modify: `src/ovpn_bot/config.py`
- Create: `tests/test_profile_naming.py`
- Create: `tests/test_state.py`
- Create: `tests/test_public_ip.py`

**Interfaces:**
- Produces: `normalize_profile_name(value: str) -> str`, `normalize_profile_suffix(value: str) -> str`, and `build_profile_filename(profile_name: str, suffix: str, protocol: str) -> str`.
- Produces: `RuntimeState`, `JsonStateStore.load()`, and `JsonStateStore.save(state)`.
- Produces: `detect_public_ipv4(fetcher=None) -> str` as an asynchronous fallback-based detector.

- [ ] **Step 1: Write failing naming tests**

```python
def test_filename_suffix_does_not_change_certificate_name():
    assert build_client_common_name("iphone", "udp") == "iphone_udp"
    assert build_profile_filename("iphone", "prague", "udp") == "iphone-prague-udp.ovpn"

def test_mismatched_text_suffix_is_not_misclassified():
    assert build_client_common_name("work_udp", "tcp") == "work_udp_tcp"
```

- [ ] **Step 2: Run the naming tests and verify missing APIs fail**

Run: `python -m pytest -q tests/test_profile_naming.py`

- [ ] **Step 3: Implement portable name and suffix validation and filename construction**

Use Latin letters, digits, `_`, and `-`; cap profile names at 32 characters and suffixes at 24 characters. Always append the selected protocol to a newly issued certificate common name.

- [ ] **Step 4: Add failing state and public-IP tests**

```python
def test_state_round_trip(tmp_path):
    store = JsonStateStore(tmp_path / "state.json")
    expected = RuntimeState(server_protocol="udp", public_host="8.8.8.8", server_port=1194, profile_suffix="prague")
    store.save(expected)
    assert store.load() == expected

def test_detector_rejects_private_then_uses_public():
    # injected fetcher returns 10.0.0.2 first and 8.8.8.8 second
    assert await detect_public_ipv4(fetcher) == "8.8.8.8"
```

- [ ] **Step 5: Implement atomic JSON persistence and public IPv4 fallback**

Write a sibling temporary file and replace the state file with `os.replace`. Validate candidates with `ipaddress.ip_address(...).is_global`.

- [ ] **Step 6: Run Task 1 tests and the existing suite**

Run: `python -c "import sys; sys.path.insert(0, 'src'); import pytest; raise SystemExit(pytest.main(['-q', 'tests']))"`

### Task 2: Single-protocol Docker lifecycle and structured profiles

**Files:**
- Modify: `src/ovpn_bot/docker_logic.py`
- Create: `tests/test_docker_commands.py`
- Modify: `tests/test_profile_protocol.py`

**Interfaces:**
- Produces: `OvpnLogic.command_init(protocol: str, host: str) -> list[str]`, which creates only `ovpn_udp` or `ovpn_tcp`.
- Produces: `OvpnLogic.list_users() -> list[UserCertificateInfo]`.
- Produces: `OvpnLogic.command_get_profile(common_name: str, protocol: str) -> bytes` and `command_revoke_common_name(common_name: str) -> str`.

- [ ] **Step 1: Write a failing command-capture test for UDP initialization**

Subclass `OvpnLogic`, record `_run_command` arguments, call `command_init("udp", "8.8.8.8")`, and assert the commands contain `ovpn_udp` and `1194:1194/udp` but never `ovpn_tcp` or a TCP port mapping.

- [ ] **Step 2: Run the focused test and confirm both containers are currently observed**

Run: `python -m pytest -q tests/test_docker_commands.py`

- [ ] **Step 3: Implement fixed protocol specifications and one server command**

Use `PROTOCOL_PORTS = {"udp": 1194, "tcp": 443}` and generate the server URL from protocol, discovered host, and fixed port. Serialize mutations with one `asyncio.Lock`.

- [ ] **Step 4: Write failing structured-list, re-download, and revoke tests**

Feed a representative EasyRSA index through the command recorder and assert valid certificates become `UserCertificateInfo` objects. Assert re-download calls only `ovpn_getclient`, and revoke accepts the exact resolved common name.

- [ ] **Step 5: Implement structured profile operations and truthful cleanup errors**

Keep the legacy string formatter as a thin wrapper over `list_users()`. Ignore missing containers during reset, but do not claim that the data volume was deleted when its command failed.

- [ ] **Step 6: Run Docker-logic tests and the full suite**

Run: `python -c "import sys; sys.path.insert(0, 'src'); import pytest; raise SystemExit(pytest.main(['-q', 'tests']))"`

### Task 3: Button-driven Telegram workflows

**Files:**
- Create: `src/ovpn_bot/telegram_ui.py`
- Rewrite: `src/ovpn_bot/telegram_bot.py`
- Create: `tests/test_telegram_ui.py`

**Interfaces:**
- Produces: `main_menu_keyboard()`, `setup_protocol_keyboard()`, `profile_actions_keyboard(users)`, and deterministic `profile_token(common_name)` helpers.
- Consumes: `JsonStateStore`, `detect_public_ipv4`, and the structured `OvpnLogic` methods from Tasks 1 and 2.

- [ ] **Step 1: Write failing keyboard and callback tests**

Assert the main reply keyboard contains the four approved Russian labels, setup has only UDP/TCP choices, and profile action callback data never contains the raw common name.

- [ ] **Step 2: Run the focused tests and verify the UI module is missing**

Run: `python -m pytest -q tests/test_telegram_ui.py`

- [ ] **Step 3: Implement keyboard builders and short deterministic profile tokens**

Use a truncated SHA-256 token. Resolve it against a freshly read active-certificate list before every download or revoke action.

- [ ] **Step 4: Add failing handler-registration and state-flow tests**

Instantiate the bot with a temporary state file and injected logic/IP detector. Assert callback and non-command text handlers are registered and that saving suffix `prague` yields `iphone-prague-udp.ovpn` without altering the certificate common name.

- [ ] **Step 5: Implement setup, creation, list, settings, download, and confirmation flows**

Use `context.user_data` only for temporary input mode and setup confirmation. Repeat admin authorization on messages and callback queries. Retain slash commands as compatibility entry points that open the same workflows.

- [ ] **Step 6: Run UI tests and the full suite**

Run: `python -c "import sys; sys.path.insert(0, 'src'); import pytest; raise SystemExit(pytest.main(['-q', 'tests']))"`

### Task 4: Reproducible Ubuntu deployment and documentation

**Files:**
- Create: `install.sh`
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `.gitignore`
- Rewrite: `README.md`

**Interfaces:**
- `install.sh` accepts no required flags, prompts for the two Telegram values, and runs `docker compose up -d --build`.
- Compose mounts `./data:/app/data`, the Docker socket, and no host Docker executable.

- [ ] **Step 1: Add the persistent data and image configuration expected by application tests**

Set `STATE_FILE=/app/data/state.json` and `OPENVPN_IMAGE=kylemanna/openvpn:2.4` in `.env.example`; ignore `data/` while retaining an optional placeholder only if needed.

- [ ] **Step 2: Update Compose and Dockerfile**

Mount application state, remove the redundant `/usr/bin/docker` bind mount, keep log rotation, and add a process health check suitable for a long-polling bot.

- [ ] **Step 3: Implement the Ubuntu installer**

Use Docker's official apt repository when `docker compose` is unavailable. Read `BOT_TOKEN` without echo, validate the token and numeric administrator ID, write `.env` with mode `600`, create `data` with mode `700`, enable Docker, build, start, and print container status.

- [ ] **Step 4: Rewrite README around the one-command path and button workflows**

Document `sudo ./install.sh`, fixed ports, automatic IP discovery, backup importance, Docker-socket risk, manual Compose fallback, tests, and compatibility commands.

- [ ] **Step 5: Validate static artifacts**

Run `docker compose --env-file .env.example config` with a temporary `.env` copy if Docker is available, and run `bash -n install.sh` where Bash is available. Do not start containers during validation.

### Task 5: Final verification

**Files:**
- Review all changed files.

- [ ] **Step 1: Run the complete test suite against the local `src` tree**

Run: `python -c "import sys; sys.path.insert(0, 'src'); import pytest; raise SystemExit(pytest.main(['-q', 'tests']))"`

- [ ] **Step 2: Compile all Python modules**

Run: `python -m compileall -q src tests`

- [ ] **Step 3: Inspect the final diff and working-tree status**

Run: `git diff --check`, `git diff --stat`, and `git status --short`.

- [ ] **Step 4: Compare every global constraint with implemented code and documentation**

Confirm one selected protocol, fixed ports, automatic IPv4, exactly two installer inputs, filename-only suffix, two-step destructive actions, persistent state, and absence of real Docker mutations in tests.

