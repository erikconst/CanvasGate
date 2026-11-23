"""Repeatable, offline browser QA against a disposable local vault."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canvasgate.web import StudioServer
from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent / 'studio-qa'
OUT.mkdir(exist_ok=True)


def until(page, predicate):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if page.evaluate(predicate):
            return
        page.wait_for_timeout(100)
    raise AssertionError('UI condition timed out: ' + predicate)


with tempfile.TemporaryDirectory() as directory:
    server = StudioServer(('127.0.0.1', 0), Path(directory))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={'width': 1600, 'height': 1050}, device_scale_factor=1)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}', wait_until='networkidle')
            page.wait_for_selector('.node')
            assert page.locator('.node').count() == 8
            page.locator('#validate').click()
            page.wait_for_timeout(200)
            page.screenshot(path=str(OUT / 'editor.png'), full_page=True)
            before = page.evaluate('() => window.canvasgateStudio.state.graph.nodes[0].x')
            node = page.locator('.node').first.bounding_box()
            page.mouse.move(node['x'] + 70, node['y'] + 28)
            page.mouse.down()
            page.mouse.move(node['x'] + 100, node['y'] + 48, steps=8)
            page.mouse.up()
            assert page.evaluate('() => window.canvasgateStudio.state.graph.nodes[0].x') != before
            page.locator('#save-flow').click()
            until(page, '() => !window.canvasgateStudio.state.dirty')
            page.locator('#run').click()
            page.locator('#modal-submit').click()
            until(page, '() => window.canvasgateStudio.state.report !== null')
            report = page.evaluate('() => window.canvasgateStudio.state.report')
            assert report['outcome'] == 'completed', report
            run_id = report['run_id']
            page.evaluate('() => window.canvasgateStudio.selectNode("plan")')
            page.locator('[data-tab="inputs"]').click()
            page.wait_for_timeout(200)
            page.screenshot(path=str(OUT / 'execution.png'), full_page=True)
            replay = page.evaluate('''async id => await window.canvasgateStudio.api('/api/runs/'+id+'/replay', {operation_key:'browser-replay'})''', run_id)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                job = page.evaluate('async id => await window.canvasgateStudio.api("/api/jobs/"+id)', replay['job_id'])
                if job['state'] in ('COMPLETED', 'FAILED'):
                    break
                page.wait_for_timeout(100)
            assert job['state'] == 'COMPLETED', job
            page.evaluate('async id => await window.canvasgateStudio.loadRun(id)', replay['run_id'])
            replay_report = page.evaluate('() => window.canvasgateStudio.state.report')
            assert replay_report['replay_comparison']['matches']
            assert replay_report['external_calls'] == 0
            page.screenshot(path=str(OUT / 'replay.png'), full_page=True)
            page.locator('[data-view="runs"]').click()
            page.screenshot(path=str(OUT / 'history.png'), full_page=True)
            note = Path(directory) / 'Studio/Specification.md'
            note.write_text(note.read_text().replace('## Policy', '## Renamed policy'))
            path = 'Studio/Order review.canvas'
            page.evaluate('async name => await window.canvasgateStudio.loadWorkflow(name)', path)
            page.locator('#run').click()
            page.locator('#modal-submit').click()
            until(page, '() => window.canvasgateStudio.state.report !== null')
            failed = page.evaluate('() => window.canvasgateStudio.state.report')
            assert failed['outcome'] != 'completed'
            assert failed['external_calls'] == 0
            page.screenshot(path=str(OUT / 'contract-failure.png'), full_page=True)
            page.set_viewport_size({'width': 390, 'height': 844})
            page.screenshot(path=str(OUT / 'mobile.png'), full_page=True)
            overflow = page.evaluate('() => document.documentElement.scrollWidth > innerWidth')
            assert not overflow, 'Mobile page overflows horizontally'
            assert not errors, errors
            (OUT / 'checks.json').write_text(json.dumps({'passed': True, 'checks': [
                '8-node graph rendered', 'validation', 'pointer drag and optimistic save',
                'mock simulation', 'actual input inspector', 'replay decision equality',
                'zero replay external calls', 'history', 'incomplete context blocked before AI',
                'mobile horizontal containment', 'no JavaScript errors'],
                'mock_report': report, 'replay_report': replay_report,
                'failure_report': failed}, indent=2), encoding='utf-8')
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        server.studio.pool.shutdown(wait=True)
        thread.join()
print('Browser QA passed; evidence:', OUT)
