#!/usr/bin/env python3
"""Offline behavior tests, including real OpenCode against a local SSE server."""
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import agent


class Transport(BaseHTTPRequestHandler):
    failures = False
    paths = []
    workspace = None

    def log_message(self, *_):
        pass

    def do_POST(self):
        type(self).paths.append(self.path)
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.failures:
            self.send_response(401)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"Invalid API key","type":"authentication_error"}}')
            return
        count = sum(1 for m in request['messages'] if m.get('role') == 'tool')
        tools = request.get('tools', [])
        sequence = [('read', {'filePath': str(self.workspace / 'add.py')}),
                    ('edit', {'filePath': str(self.workspace / 'add.py'),
                              'oldString': 'return a - b', 'newString': 'return a + b'}),
                    ('bash', {'command': 'python3 -m unittest', 'description': 'Run tests'})]
        delta = {'role': 'assistant', 'content': 'Completed; check the actual test result.'}
        finish = 'stop'
        if tools and count < len(sequence):
            name, args = sequence[count]
            delta = {'role': 'assistant', 'tool_calls': [{'index': 0, 'id': f'call_{count}',
                'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}
            finish = 'tool_calls'
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        for chunk in [
            {'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]},
            {'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]},
            {'choices': [], 'usage': {'prompt_tokens': 50, 'completion_tokens': 10, 'total_tokens': 60}},
        ]:
            chunk.update(id='mock', model=agent.MODEL, object='chat.completion.chunk', created=1)
            self.wfile.write(('data: ' + json.dumps(chunk) + '\n\n').encode())
        self.wfile.write(b'data: [DONE]\n\n')


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='tokenme-tests-')
        self.root = Path(self.tmp.name).resolve()
        self.env = patch.dict(os.environ, {'TOKENME_API_KEY': 'offline-test-secret'})
        self.env.start()
        self.root_patch = patch.object(agent, 'ROOT', self.root / 'runtime')
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.env.stop()
        self.tmp.cleanup()

    def test_credentials_missing_and_override(self):
        self.assertEqual(agent.credential(), 'offline-test-secret')
        with patch.dict(os.environ, {'TOKENME_API_KEY': ''}), patch.object(agent.subprocess, 'run',
                return_value=subprocess.CompletedProcess([], 1, '', 'locked')):
            with self.assertRaisesRegex(ValueError, 'Credential unavailable'):
                agent.credential()

    def test_model_requires_limits(self):
        with patch.dict(os.environ, {'TOKENME_MODEL': 'other-model'}):
            with self.assertRaisesRegex(ValueError, 'explicit'):
                agent.config([], [], 20)

    def test_permissions_and_path_validation(self):
        for pattern in ('../secret', '/tmp/secret', ''):
            with self.assertRaises(ValueError):
                agent.config([pattern], [], 20)
        with self.assertRaises(ValueError):
            agent.config([], ['python3 *'], 20)
        cfg = agent.config(['add.py'], ['python3 -m unittest'], 20)
        self.assertEqual(cfg['permission']['edit'], {'*': 'deny', 'add.py': 'allow'})
        self.assertEqual(cfg['permission']['*'], 'deny')

    def test_redaction_and_timeout(self):
        self.assertNotIn('secret', json.dumps(agent.redact({'error': ['secret']}, 'secret')))
        code, _, _ = agent.process([sys.executable, '-c', 'import time; time.sleep(5)'],
                                  os.environ.copy(), self.root, 0.1)
        self.assertEqual(code, 124)

    def test_config_override_rejected(self):
        cfg = agent.config([], [], 20)
        bad = json.loads(json.dumps(cfg))
        bad['permission']['task'] = 'allow'
        with patch.object(agent, 'process', side_effect=[(0, '1.19.5', ''), (0, json.dumps(bad), '')]):
            with self.assertRaisesRegex(ValueError, 'permission'):
                agent.preflight(cfg, {}, self.root)

    def test_workspace_lock(self):
        (agent.ROOT / 'locks').mkdir(parents=True)
        path = agent.ROOT / 'locks' / hashlib.sha256(str(self.root).encode()).hexdigest()
        with path.open('w') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, 'already owns'):
                agent.run(self.root, 'task', [], [])

    def fixture(self):
        workspace = self.root / 'project'
        workspace.mkdir()
        (workspace / 'add.py').write_text('def add(a, b):\n    return a - b\n')
        (workspace / 'test_add.py').write_text('import unittest\nfrom add import add\nclass Test(unittest.TestCase):\n    def test_add(self): self.assertEqual(add(2,3),5)\n')
        return workspace

    def serve(self, workspace, fail=False):
        handler = type('Handler', (Transport,), {'workspace': workspace, 'failures': fail, 'paths': []})
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server, handler

    def test_real_opencode_tool_cycle_and_conflicting_project_config(self):
        workspace = self.fixture()
        (workspace / 'opencode.json').write_text(json.dumps({'model': 'wrong/model', 'permission': 'allow'}))
        server, handler = self.serve(workspace)
        try:
            with patch.dict(os.environ, {'TOKENME_BASE_URL': f'http://127.0.0.1:{server.server_port}/v1'}):
                result = agent.run(workspace, 'Fix add.py and run the tests.', ['add.py'], ['python3 -m unittest'], timeout=30)
            self.assertEqual(result['status'], 'returned', result)
            self.assertIn('return a + b', (workspace / 'add.py').read_text())
            self.assertEqual(result['changed_files'], ['add.py'])
            self.assertIn('return a - b', (Path(result['artifacts']) / 'before/add.py').read_text())
            self.assertTrue(all(p == '/v1/chat/completions' for p in handler.paths), handler.paths)
            self.assertNotIn('offline-test-secret', ''.join(p.read_text() for p in Path(result['artifacts']).rglob('*') if p.is_file()))
        finally:
            server.shutdown()
            server.server_close()

    def test_real_opencode_auth_failure(self):
        workspace = self.fixture()
        server, _ = self.serve(workspace, fail=True)
        try:
            with patch.dict(os.environ, {'TOKENME_BASE_URL': f'http://127.0.0.1:{server.server_port}/v1'}):
                result = agent.run(workspace, 'Fix add.py.', ['add.py'], [], timeout=15)
            self.assertEqual(result['status'], 'failed', result)
            self.assertEqual(result['changed_files'], [])
        finally:
            server.shutdown()
            server.server_close()

    def test_nested_git_worktree_permissions(self):
        workspace = self.fixture()
        subprocess.run(['git', 'init', '-q', str(workspace)], check=True)
        subprocess.run(['git', '-C', str(workspace), '-c', 'user.name=Offline Test',
                        '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty',
                        '-qm', 'fixture'], check=True)
        nested = workspace / 'package'
        nested.mkdir()
        for name in ('add.py', 'test_add.py'):
            (workspace / name).rename(nested / name)
        server, _ = self.serve(nested)
        try:
            with patch.dict(os.environ, {'TOKENME_BASE_URL': f'http://127.0.0.1:{server.server_port}/v1'}):
                result = agent.run(nested, 'Fix add.py and run tests.', ['add.py'], ['python3 -m unittest'], timeout=30)
            self.assertEqual(result['status'], 'returned', result)
            self.assertIn('return a + b', (nested / 'add.py').read_text())
        finally:
            server.shutdown()
            server.server_close()

    def test_malformed_output_and_tool_errors_are_not_success(self):
        workspace = self.fixture()
        for output, expected in [('not JSON', 'failed'),
            (json.dumps({'type': 'text', 'part': {'text': 'done'}}) + '\n' + json.dumps(
                {'type': 'tool_use', 'part': {'tool': 'edit', 'state': {'status': 'error'}}}), 'blocked')]:
            with patch.object(agent, 'preflight'), patch.object(agent, 'process', return_value=(0, output, '')):
                result = agent.run(workspace, 'task', [], [])
            self.assertEqual(result['status'], expected)

    def test_denied_edit_does_not_modify_file(self):
        workspace = self.fixture()
        server, _ = self.serve(workspace)
        try:
            with patch.dict(os.environ, {'TOKENME_BASE_URL': f'http://127.0.0.1:{server.server_port}/v1'}):
                result = agent.run(workspace, 'Fix add.py.', [], [], steps=4, timeout=20)
            self.assertIn('return a - b', (workspace / 'add.py').read_text())
            self.assertEqual(result['changed_files'], [])
            self.assertIn(result['status'], ('blocked', 'failed'), result)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
