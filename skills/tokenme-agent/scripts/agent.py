#!/usr/bin/env python3
"""Thin, isolated OpenCode launcher. Python standard library only."""
import argparse
import fcntl
import fnmatch
import getpass
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path.home() / '.local/share/tokenme-agent'
MODEL = 'deepseek-ai/deepseek-v4-flash-0731'
SERVICE = 'codex-tokenme-agent'


def credential():
    if os.environ.get('TOKENME_API_KEY'):
        return os.environ['TOKENME_API_KEY']
    p = subprocess.run(['/usr/bin/security', 'find-generic-password', '-s', SERVICE,
                        '-a', 'TOKENME_API_KEY', '-w'], capture_output=True, text=True)
    if p.returncode or not p.stdout.strip():
        raise ValueError('Credential unavailable: set TOKENME_API_KEY or run set-key.')
    return p.stdout.strip()


def redact(value, key):
    if isinstance(value, str):
        return value.replace(key, '[REDACTED]') if key else value
    if isinstance(value, list):
        return [redact(x, key) for x in value]
    if isinstance(value, dict):
        return {k: redact(v, key) for k, v in value.items()}
    return value


def config(edits, commands, steps, workspace=None):
    model = os.environ.get('TOKENME_MODEL', MODEL)
    if model != MODEL and not all(os.environ.get(k) for k in
                                  ('TOKENME_CONTEXT_TOKENS', 'TOKENME_OUTPUT_TOKENS')):
        raise ValueError('A different model requires explicit context and output limits.')
    context = int(os.environ.get('TOKENME_CONTEXT_TOKENS', '1048576'))
    output = int(os.environ.get('TOKENME_OUTPUT_TOKENS', '32768'))
    if not 0 < output < context:
        raise ValueError('Limits must satisfy 0 < output < context.')
    for pattern in edits:
        if Path(pattern).is_absolute() or '..' in Path(pattern).parts or not pattern:
            raise ValueError('Edit patterns must be nonempty workspace-relative paths.')
    # edit/write/patch permissions use paths relative to Instance.worktree,
    # which is the repository root, or '/' for non-Git directories.
    permission_edits = edits
    if workspace:
        git = subprocess.run(['git', '-C', str(workspace), 'rev-parse', '--show-toplevel'],
                             capture_output=True, text=True)
        base = Path(git.stdout.strip()).resolve() if git.returncode == 0 else Path('/')
        permission_edits = [os.path.relpath(Path(workspace) / x, base) for x in edits]
    perms = {'*': 'deny', 'read': {'*': 'allow', '*.env': 'deny', '*.env.*': 'deny'},
             'glob': 'allow', 'grep': 'allow',
             'edit': {'*': 'deny', **{x: 'allow' for x in permission_edits}},
             'bash': {'*': 'deny', **{x: 'allow' for x in commands}},
             'external_directory': 'deny', 'doom_loop': 'deny'}
    if any(x in ('*', '') or any(c in x for c in '*?\n\r') for x in commands):
        raise ValueError('Check commands must be explicit, without wildcard permission patterns.')
    return {'model': 'tokenme/' + model, 'small_model': 'tokenme/' + model,
            'enabled_providers': ['tokenme'], 'autoupdate': False, 'share': 'disabled',
            'snapshot': False, 'lsp': False, 'formatter': False, 'plugin': [], 'mcp': {},
            'permission': perms,
            'provider': {'tokenme': {'npm': '@ai-sdk/openai-compatible',
                'options': {'baseURL': os.environ.get('TOKENME_BASE_URL',
                    'https://api.tokenme.limited/api/v1'), 'apiKey': '{env:TOKENME_API_KEY}'},
                'models': {model: {'name': model, 'tool_call': True,
                    'limit': {'context': context, 'input': context, 'output': output}}}}},
            'agent': {'tokenme-worker': {'mode': 'primary', 'description': 'Scoped coding worker',
                'steps': steps, 'permission': perms,
                'prompt': 'Implement only the supplied task. Follow its project instructions. '
                          'Use only permitted paths and commands. Run the requested checks. '
                          'Report changed files, actual check outcomes, and blockers. '
                          'When blocked, return the blocker instead of seeking extra tools.'}}}


def environment(cfg, key):
    # Pinned OpenCode also discovers ~/.opencode via Global.Path.home; isolate that
    # lookup with its supported internal test-home hook without repurposing HOME.
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    ROOT.chmod(0o700)
    env = {k: v for k, v in os.environ.items() if not k.startswith('OPENCODE_')}
    for kind in ('CONFIG', 'DATA', 'CACHE', 'STATE'):
        path = ROOT / kind.lower()
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        env['XDG_' + kind + '_HOME'] = str(path)
    isolated_home = ROOT / 'discovery'
    isolated_home.mkdir(parents=True, exist_ok=True, mode=0o700)
    env.update(TOKENME_API_KEY=key, OPENCODE_CONFIG_CONTENT=json.dumps(cfg),
               OPENCODE_TEST_HOME=str(isolated_home), OPENCODE_DISABLE_PROJECT_CONFIG='1',
               OPENCODE_DISABLE_EXTERNAL_SKILLS='1', OPENCODE_DISABLE_CLAUDE_CODE='1',
               OPENCODE_DISABLE_MODELS_FETCH='1', OPENCODE_DISABLE_AUTOUPDATE='1',
               OPENCODE_PURE='1')
    return env


def process(argv, env, cwd, timeout):
    p = subprocess.Popen(argv, env=env, cwd=cwd, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout)
        return p.returncode, out, err
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
        os.killpg(p.pid, signal.SIGTERM)
        try:
            out, err = p.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            out, err = p.communicate()
        return (124 if isinstance(exc, subprocess.TimeoutExpired) else 130), out, err


def preflight(cfg, env, workspace):
    if not shutil.which('opencode'):
        raise ValueError('OpenCode missing. Install npm package opencode-ai@1.19.5.')
    code, version, _ = process(['opencode', '--version'], env, workspace, 30)
    if code or version.strip() != '1.19.5':
        raise ValueError('This launcher requires OpenCode 1.19.5.')
    code, out, _ = process(['opencode', 'debug', 'config', '--pure'], env, workspace, 60)
    if code:
        raise ValueError('Resolved config inspection failed (details suppressed to protect credentials).')
    resolved = json.loads(out)
    for field in ('model', 'small_model', 'enabled_providers', 'permission'):
        if resolved.get(field) != cfg[field]:
            raise ValueError('Unexpected resolved configuration: ' + field)
    worker = resolved.get('agent', {}).get('tokenme-worker', {})
    if worker.get('permission') != cfg['permission'] or worker.get('steps') != cfg['agent']['tokenme-worker']['steps']:
        raise ValueError('Worker permissions or step limit were overridden.')
    provider = resolved.get('provider', {}).get('tokenme', {})
    if (provider.get('npm') != '@ai-sdk/openai-compatible' or
            provider.get('options', {}).get('baseURL') != cfg['provider']['tokenme']['options']['baseURL'] or
            provider.get('models') != cfg['provider']['tokenme']['models'] or
            resolved.get('plugin') or resolved.get('mcp')):
        raise ValueError('Unexpected provider, limits, plugins, or MCP configuration.')


def inventory(workspace):
    p = subprocess.run(['git', '-C', str(workspace), 'ls-files', '-co', '--exclude-standard', '-z'],
                       capture_output=True)
    if p.returncode == 0:
        paths = sorted(set(os.fsdecode(x) for x in p.stdout.split(b'\0') if x))
    else:
        paths = [str(p.relative_to(workspace)) for p in workspace.rglob('*')
                 if not any(x in ('.git', 'node_modules', '__pycache__') for x in p.relative_to(workspace).parts)]
    result = {}
    for rel in paths:
        p = workspace / rel
        if p.is_symlink():
            result[rel] = {'symlink': os.readlink(p)}
        elif p.is_file():
            result[rel] = {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'size': p.stat().st_size}
    return result


def run(workspace, task, edits, commands, steps=20, timeout=600):
    workspace = Path(workspace).resolve(strict=True)
    if not workspace.is_dir() or workspace == Path.home():
        raise ValueError('Use a project directory, not the home directory.')
    if not task.strip():
        raise ValueError('Task must not be empty.')
    key = credential()
    cfg = config(edits, commands, steps, workspace)
    env = environment(cfg, key)
    locks = ROOT / 'locks'
    locks.mkdir(exist_ok=True)
    lock = (locks / hashlib.sha256(str(workspace).encode()).hexdigest()).open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise ValueError('A worker already owns this workspace.')
    try:
        preflight(cfg, env, workspace)
        runs = ROOT / 'runs'
        runs.mkdir(exist_ok=True)
        artifact = Path(tempfile.mkdtemp(prefix='run-', dir=runs))
        before = inventory(workspace)
        baseline = artifact / 'before'
        baseline.mkdir()
        for rel in before:
            if any(fnmatch.fnmatchcase(rel, pat) for pat in edits):
                p = workspace / rel
                if p.is_file() and not p.is_symlink():
                    target = baseline / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(p, target)
        git = subprocess.run(['git', '-C', str(workspace), 'status', '--porcelain=v1', '-z'], capture_output=True)
        (artifact / 'git-status-before.bin').write_bytes(git.stdout)
        scoped_task = (f'Workspace: {workspace}\nAllowed edit patterns: {json.dumps(edits)}\n'
                       f'Only allowed shell commands: {json.dumps(commands)}\n'
                       'Use read/glob/grep for inspection. Other tools are denied. '
                       'If a required permission is denied, stop and report the blocker.\n\n' + task)
        code, out, err = process(['opencode', 'run', '--pure', '--dir', str(workspace),
                                  '--agent', 'tokenme-worker', '--model', cfg['model'],
                                  '--format', 'json', scoped_task], env, workspace, timeout)
        after = inventory(workspace)
        for name, value in (('before.json', before), ('after.json', after)):
            (artifact / name).write_text(json.dumps(value, indent=2))
        (artifact / 'events.jsonl').write_text(redact(out, key))
        (artifact / 'stderr.log').write_text(redact(err, key))
        events, malformed = [], False
        for line in out.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError()
                events.append(event)
            except (ValueError, TypeError):
                malformed = True
        errors = [e.get('error') for e in events if e.get('type') == 'error']
        tools = [e['part'] for e in events if e.get('type') == 'tool_use' and isinstance(e.get('part'), dict)]
        failures = [p for p in tools if p.get('state', {}).get('status') == 'error']
        texts = [e.get('part', {}).get('text', '') for e in events if e.get('type') == 'text']
        changed = [p for p in sorted(before.keys() | after.keys()) if before.get(p) != after.get(p)]
        unexpected = [p for p in changed if not any(fnmatch.fnmatchcase(p, pat) for pat in edits)]
        status = 'timeout' if code == 124 else 'cancelled' if code == 130 else (
            'failed' if code or errors or malformed or not texts else 'blocked' if failures else 'returned')
        result = {'status': status, 'exit_code': code, 'text': '\n'.join(texts),
                  'errors': errors, 'tool_failures': failures, 'changed_files': changed,
                  'outside_edit_patterns': unexpected, 'artifacts': str(artifact),
                  'usage': [e.get('part', {}).get('tokens') for e in events if e.get('type') == 'step_finish']}
        return redact(result, key)
    finally:
        lock.close()


def live():
    with tempfile.TemporaryDirectory(prefix='tokenme-smoke-') as directory:
        workspace = Path(directory).resolve()
        (workspace / 'add.py').write_text('def add(a, b):\n    return a - b\n')
        (workspace / 'test_add.py').write_text('import unittest\nfrom add import add\nclass TestAdd(unittest.TestCase):\n    def test_add(self): self.assertEqual(add(2, 3), 5)\n')
        task = (f'Fix {workspace}/add.py so add(a,b) adds the numbers. '
                'Only edit add.py. Read that exact file directly with read (no discovery needed), '
                'edit it using edit, then run '
                'python3 -m unittest using the bash tool. Report the observed result.')
        result = run(workspace, task, ['add.py'], ['python3 -m unittest'], timeout=180)
        check = subprocess.run(['python3', '-m', 'unittest'], cwd=directory, capture_output=True)
        events = [json.loads(line) for line in (Path(result['artifacts']) / 'events.jsonl').read_text().splitlines() if line.startswith('{')]
        tools = [e.get('part', {}).get('tool') for e in events if e.get('type') == 'tool_use']
        result['live_verified'] = (result['status'] == 'returned' and check.returncode == 0
                                   and 'bash' in tools and any(t in tools for t in ('edit', 'write', 'apply_patch')))
        result['tools_observed'] = tools
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    d = sub.add_parser('doctor')
    d.add_argument('--live', action='store_true')
    sub.add_parser('set-key')
    r = sub.add_parser('run')
    r.add_argument('--workspace', required=True)
    r.add_argument('--task-file', required=True)
    r.add_argument('--allow-edit', action='append', default=[])
    r.add_argument('--allow-command', action='append', default=[])
    r.add_argument('--steps', type=int, default=20)
    r.add_argument('--timeout', type=float, default=600)
    args = parser.parse_args()
    try:
        if args.mode == 'set-key':
            key = getpass.getpass('TokenMe API key: ')
            if not key or any(c in key for c in '\r\n"\\'):
                raise ValueError('Invalid key characters.')
            command = f'add-generic-password -U -s {SERVICE} -a TOKENME_API_KEY -w "{key}"\n'
            subprocess.run(['/usr/bin/security', '-i'], input=command, capture_output=True, text=True, check=True)
            print(json.dumps({'credential_stored': credential() == key}))
            return
        if args.mode == 'doctor':
            if args.live:
                result = live()
            else:
                key = credential()
                cfg = config([], [], 20)
                with tempfile.TemporaryDirectory(prefix='tokenme-doctor-') as directory:
                    preflight(cfg, environment(cfg, key), directory)
                result = {'ready': True, 'runtime': '1.19.5', 'model': cfg['model'], 'live_verified': False}
        else:
            if not 1 <= args.steps <= 100 or args.timeout <= 0:
                raise ValueError('Use 1–100 steps and a positive timeout.')
            result = run(args.workspace, Path(args.task_file).read_text(), args.allow_edit,
                         args.allow_command, args.steps, args.timeout)
        print(json.dumps(result, ensure_ascii=False))
        if result.get('status') in ('failed', 'timeout', 'cancelled', 'blocked') or result.get('live_verified') is False and args.mode == 'doctor' and args.live:
            sys.exit(1)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        # Never surface subprocess output, resolved config, headers, or credential values.
        print(json.dumps({'status': 'failed', 'error': str(exc) if isinstance(exc, ValueError) else type(exc).__name__}))
        sys.exit(1)


if __name__ == '__main__':
    main()
