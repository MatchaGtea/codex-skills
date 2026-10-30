---
name: tokenme-agent
description: Delegate well-scoped coding work to DeepSeek through TokenMe and OpenCode. Use for implementing an agreed specification, mechanical refactors, focused tests, or when the user requests a TokenMe coding helper. Keep architecture and ambiguous debugging decisions with Codex.
---

# TokenMe Agent

Codex owns the plan and acceptance; OpenCode runs the delegated task. Use `scripts/agent.py` with Python 3. No shell alias is needed.

## Prepare

Run `python3 <skill-dir>/scripts/agent.py doctor` to check the runtime, credential availability, and resolved config. `doctor --live` also exercises TokenMe with a small file-editing and testing task in a temporary directory; it consumes API tokens.

Credentials come from `TOKENME_API_KEY`, otherwise macOS Keychain service `codex-tokenme-agent`, account `TOKENME_API_KEY`. Run `agent.py set-key` to set or replace the Keychain item interactively. Keep keys out of task files and command arguments.

## Delegate

Write a self-contained UTF-8 task file outside the project. Include the agreed change, absolute workspace path, relevant project instructions, allowed outputs, and acceptance criteria. Read applicable AGENTS.md files yourself and pass relevant requirements: automatic project instruction discovery is disabled in the worker. Supply necessary context rather than the conversation history or a whole-repository dump.

```bash
python3 <skill-dir>/scripts/agent.py run \
  --workspace /absolute/project \
  --task-file /absolute/task.md \
  --allow-edit 'src/example.py' \
  --allow-command 'python3 -m unittest'
```

Repeat `--allow-edit` for workspace-relative files/globs and `--allow-command` for exact trusted check commands. The worker can read/search the workspace, edit listed paths, and run selected commands. Other tools, external-directory access, and nested delegation are denied. These permissions are not an OS sandbox: check commands execute project code and may create normal generated artifacts. Select commands consistent with the user's authorization.

One worker runs per workspace, limited to 20 steps and 600 seconds by default. Override `--steps` or `--timeout` only when warranted. Avoid editing the same files concurrently.

## Accept

The launcher returns compact JSON: status, final text, tool failures, token usage when available, changed files, and an artifact directory with baseline evidence and sanitized events. `returned` means the worker returned, not that the task passed. Verify the actual diff against the baseline and acceptance criteria, including new/untracked files. Inspect recorded check results and independently verify where needed.

Delegate at most one focused correction with failure evidence. Then take over or report the blocker. Authentication/config errors require resolving the cause, not silently switching models. After cancellation/timeout inspect partial edits and artifacts; the launcher preserves files rather than rolling them back.

The default model is `deepseek-ai/deepseek-v4-flash-0731`, with context/input ceiling 1,048,576 and output ceiling 32,768 tokens (user-supplied limits). `TOKENME_BASE_URL` overrides the endpoint for local testing. A different `TOKENME_MODEL` requires explicit `TOKENME_CONTEXT_TOKENS` and `TOKENME_OUTPUT_TOKENS`.

Config and state are isolated under `~/.local/share/tokenme-agent`; normal OpenCode and shell settings remain untouched. Run `scripts/test_agent.py` for offline transport, permission, and process tests.
