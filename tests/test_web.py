import http.client
import contextlib
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.parse import quote

from canvasgate.web import StudioServer
from canvasgate.cli import main as cli_main
from canvasgate.transactions import TransactionStore


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp.name)
        self.server = StudioServer(('127.0.0.1', 0), self.vault)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f'http://127.0.0.1:{self.server.server_port}'
        self.cookie = ''
        self.csrf = ''
        status, headers, _ = self.request('GET', '/')
        self.assertEqual(status, 200)
        self.cookie = headers['Set-Cookie'].split(';')[0]
        _, _, boot = self.request('GET', '/api/bootstrap')
        self.csrf = boot['csrf']
        self.path = boot['default_workflow']
        _, _, self.flow = self.request('GET', '/api/workflow?path=' + quote(self.path))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server.studio.pool.shutdown(wait=True)
        self.thread.join()
        self.temp.cleanup()

    def request(self, method, path, body=None, **overrides):
        headers = {'Cookie': self.cookie, 'Origin': self.origin, 'X-CSRF-Token': self.csrf,
                   'Content-Type': 'application/json'}
        headers.update(overrides)
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        conn.request(method, path, None if body is None else json.dumps(body), headers)
        response = conn.getresponse()
        data = response.read()
        result_headers = dict(response.getheaders())
        result = json.loads(data) if 'application/json' in result_headers.get('Content-Type', '') else data
        status = response.status
        conn.close()
        return status, result_headers, result

    def finish(self, job):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            _, _, current = self.request('GET', '/api/jobs/' + job['job_id'])
            if current['state'] in ('COMPLETED', 'FAILED'):
                self.assertEqual(current['state'], 'COMPLETED', current)
                return current
            time.sleep(.02)
        self.fail('Job did not finish')

    def run_mock(self, key='test-operation'):
        body = {'path': self.path, 'expected_sha256': self.flow['sha256'], 'operation_key': key,
                'backend': 'mock', 'strict_isolation': True, 'commit': False}
        status, _, job = self.request('POST', '/api/runs', body)
        self.assertEqual(status, 202, job)
        self.finish(job)
        return body, job

    def test_http_security(self):
        self.assertEqual(self.request('GET', '/api/bootstrap', Cookie='')[0], 401)
        self.assertEqual(self.request('GET', '/', Host='attacker.example')[0], 400)
        self.assertEqual(self.request('GET', '/', Origin='https://attacker.example')[0], 400)
        self.assertEqual(self.request('POST', '/api/validate', {}, **{'X-CSRF-Token': ''})[0], 403)
        self.assertEqual(self.request('POST', '/api/validate', {}, Origin='')[0], 400)
        _, headers, _ = self.request('GET', '/')
        self.assertNotIn('unsafe-eval', headers['Content-Security-Policy'])
        self.assertIn('HttpOnly', headers['Set-Cookie'])

    def test_private_paths(self):
        (self.vault / '.env').write_text('PRIVATE_VALUE=hidden')
        for name in ('../outside.md', '.env', '.canvasgate/runs/private.json'):
            status, _, _ = self.request('GET', '/api/source?path=' + quote(name))
            self.assertEqual(status, 400)

    def test_optimistic_edits(self):
        _, _, source = self.request('GET', '/api/source?path=Studio/Specification.md')
        body = {'path': source['path'], 'text': source['text'] + '\nEditorial note.\n', 'expected_sha256': source['sha256']}
        self.assertEqual(self.request('POST', '/api/source/save', body)[0], 200)
        self.assertEqual(self.request('POST', '/api/source/save', body)[0], 400)
        graph = {'path': self.path, 'graph': self.flow['graph'], 'expected_sha256': self.flow['sha256']}
        graph['graph']['nodes'][0]['x'] += 20
        self.assertEqual(self.request('POST', '/api/workflow/save', graph)[0], 200)
        self.assertEqual(self.request('POST', '/api/workflow/save', graph)[0], 400)

    def test_validation_and_explicit_pins(self):
        body = {'path': self.path, 'graph': self.flow['graph']}
        self.assertTrue(self.request('POST', '/api/validate', body)[2]['valid'])
        note = self.vault / 'Studio/Specification.md'
        note.write_text(note.read_text().replace('revision: 3', 'revision: 4'))
        status, _, pinned = self.request('POST', '/api/contracts/pin', body)
        self.assertEqual(status, 200)
        required = pinned['graph']['canvasgate']['contracts']['plan']['input']['required_sources'][0]
        self.assertEqual(required['version']['equals'], 3)
        self.assertNotEqual(required['sha256'], body['graph']['canvasgate']['contracts']['plan']['input']['required_sources'][0]['sha256'])

    def test_run_dedup_replay_and_bundle(self):
        body, job = self.run_mock()
        self.assertEqual(self.request('POST', '/api/runs', body)[2]['job_id'], job['job_id'])
        self.assertEqual(self.request('POST', '/api/runs', {**body, 'commit': True})[0], 400)
        _, _, detail = self.request('GET', '/api/runs/' + job['run_id'])
        self.assertEqual(detail['report']['outcome'], 'completed')
        status, _, replay = self.request('POST', '/api/runs/' + job['run_id'] + '/replay', {'operation_key': 'replay-operation'})
        self.assertEqual(status, 202)
        self.finish(replay)
        _, _, result = self.request('GET', '/api/runs/' + replay['run_id'])
        self.assertTrue(result['report']['replay_comparison']['matches'])
        self.assertEqual(result['report']['external_calls'], 0)
        self.assertFalse(result['report']['written_files'])
        status, _, bundle = self.request('GET', '/api/runs/' + job['run_id'] + '/bundle')
        self.assertEqual(status, 200)
        self.assertTrue(bundle['sources'])
        self.assertEqual(len(bundle['nodes']), 8)
        self.assertTrue((self.vault / 'Studio/Runs' / job['run_id'] / 'Inspect.canvas').exists())

    def test_contract_failure_before_model(self):
        note = self.vault / 'Studio/Specification.md'
        note.write_text(note.read_text().replace('## Policy', '## Renamed policy'))
        _, job = self.run_mock()
        _, _, detail = self.request('GET', '/api/runs/' + job['run_id'])
        self.assertNotEqual(detail['report']['outcome'], 'completed')
        self.assertEqual(detail['report']['external_calls'], 0)

    def test_strict_cli_rejected(self):
        status, _, result = self.request('POST', '/api/runs', {'path': self.path,
            'expected_sha256': self.flow['sha256'], 'backend': 'codex', 'strict_isolation': True})
        self.assertEqual(status, 400)
        self.assertIn('isolat', result['error'].lower())

    def test_reconciliation_refuses_active_execution(self):
        _, job = self.run_mock()
        with TransactionStore(self.vault).lock('run-locks/' + job['run_id'] + '.lock'):
            status, _, result = self.request('POST', '/api/runs/' + job['run_id'] + '/reconcile',
                {'effect_id': 'unknown', 'action': 'authorize_retry'})
        self.assertEqual(status, 400)
        self.assertIn('lock', result['error'])

    def test_cli_replay_never_requires_live_provider_configuration(self):
        _, job = self.run_mock()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = cli_main([str(self.vault / 'deleted.canvas'), '--vault', str(self.vault),
                '--replay', job['run_id'], '--backend', 'api', '--output-dir', str(self.vault / 'cli-report')])
        self.assertEqual(code, 0)
