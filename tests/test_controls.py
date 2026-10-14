"""Exercise real subprocess ordering and HTTP boundaries without a paid Claude turn."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from driver import Driver
from sessions import Session
import server

ROOT = Path(__file__).resolve().parents[1]

class Sessions:
    def __init__(self):
        self.pending, self.all = {}, {}
    def add_pending(self, sid, cwd):
        self.pending[sid] = {'id':sid, 'cwd':cwd}
    def find_path(self, sid):
        return None
    def adopt(self, sid):
        return None

class Controls(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.events = []
        self.sessions = Sessions()
        self.driver = Driver(ROOT, self.root, self.sessions, self.events.append, lambda:'')
        self.driver.claude = str(ROOT / 'tests/fake_claude.py')
        self.sid = self.driver.start(str(self.root))
    async def asyncTearDown(self):
        await self.driver.close()
        self.tmp.cleanup()
    async def until(self, fn):
        async with asyncio.timeout(10):
            while not fn():
                await asyncio.sleep(.01)
    async def test_persistent_turns_and_usage(self):
        await self.driver.send(self.sid, 'first')
        proc = self.driver.running[self.sid]
        await self.until(lambda:self.sid not in self.driver.busy)
        await self.driver.send(self.sid, 'second')
        await self.until(lambda:self.sid not in self.driver.busy)
        self.assertIs(self.driver.running[self.sid], proc)
        self.assertIsNone(proc.returncode)
        self.assertEqual(self.driver.usage[self.sid]['output'], 8)
        self.assertEqual([e['text'] for e in self.events if e['t']=='delta'], ['first','second'])
    async def test_correction_waits_for_interrupted_result(self):
        await self.driver.send(self.sid, 'hold')
        proc = self.driver.running[self.sid]
        await self.driver.interrupt(self.sid, 'corrected')
        await self.until(lambda:any(e.get('text')=='corrected' for e in self.events))
        end = next(i for i,e in enumerate(self.events) if e['t']=='turn_end')
        reply = next(i for i,e in enumerate(self.events) if e.get('text')=='corrected')
        self.assertLess(end, reply)
        self.assertTrue(self.events[end]['stopped'])
        self.assertIs(self.driver.running[self.sid], proc)
    async def test_unresponsive_stop_resumes_correction(self):
        await self.driver.send(self.sid, 'ignore')
        proc = self.driver.running[self.sid]
        await self.driver.interrupt(self.sid, 'after kill')
        await self.until(lambda:any(e.get('text')=='after kill' for e in self.events))
        self.assertIsNotNone(proc.returncode)
        self.assertIsNot(self.driver.running[self.sid], proc)
    async def test_permission_snapshot_and_cancel(self):
        await self.driver.send(self.sid, 'permission')
        await self.until(lambda:bool(self.driver.permissions))
        p = self.driver.snapshot()['permissions'][0]
        self.assertEqual(p['session'], self.sid)
        self.assertIn(self.sid, self.driver.busy)
        await self.driver.interrupt(self.sid)
        await self.until(lambda:self.sid not in self.driver.busy)
        self.assertFalse(self.driver.snapshot()['permissions'])
        with self.assertRaises(RuntimeError):
            await self.driver.answer(self.sid, p['id'], True)
        self.assertTrue(any('"behavior": "deny"' in e.get('text','') for e in self.events))
    async def test_question_requires_answer_then_continues(self):
        await self.driver.send(self.sid, 'question')
        await self.until(lambda:bool(self.driver.permissions))
        with self.assertRaises(RuntimeError):
            await self.driver.answer(self.sid, 'request-1', True, {})
        await self.driver.answer(self.sid, 'request-1', True, {'Proceed?':'No'})
        await self.until(lambda:self.sid not in self.driver.busy)
        self.assertTrue(any('"Proceed?": "No"' in e.get('text','') for e in self.events))
    async def test_sessions_are_independent(self):
        other = self.driver.start(str(self.root))
        await self.driver.send(self.sid, 'hold')
        await self.driver.send(other, 'other')
        await self.until(lambda:other not in self.driver.busy)
        self.assertIn(self.sid, self.driver.busy)
        await self.driver.interrupt(self.sid)
        await self.until(lambda:self.sid not in self.driver.busy)
        self.assertIsNone(self.driver.running[other].returncode)
    async def test_native_usage_event(self):
        await self.driver._event(self.sid, {'type':'rate_limit_event', 'rate_limit_info':{'rateLimitType':'five_hour', 'utilization':.25, 'resetsAt':12345}})
        self.assertEqual(self.driver.snapshot()['usageWindows']['five_hour']['utilization'], .25)
        self.assertNotIn('seven_day', self.driver.usage_windows)
    async def test_log_replay_does_not_hide_stop_or_lock_idle_session(self):
        path = self.root / 'log.jsonl'
        path.touch()
        s = Session(path, None, self.events.append)
        s.managed = True
        s.driving = True
        self.assertTrue(s.meta()['driving'])
        s.driving = False
        s.open = True  # interrupted turn's delayed tool-result log
        self.assertFalse(s.meta()['working'])
        s.managed = False
        self.assertTrue(s.meta()['working'])
    async def test_http_explicit_permission_origin_and_preview_scope(self):
        app = web.Application()
        app.router.add_post('/api/session/{id}/permission/{rid}', server.answer)
        app.router.add_post('/api/session/{id}/interrupt', server.interrupt)
        app.router.add_get('/api/session/{id}/preview', server.preview)
        note = self.root / 'note.md'
        note.write_text('# Safe preview')
        link = self.root / 'escape'
        link.symlink_to('/etc/passwd')
        with patch.object(server,'driver',self.driver), patch.object(server,'sessions',self.sessions), patch.object(server,'VAULT',self.root), patch.object(server,'load_repos',lambda:[]):
            async with TestClient(TestServer(app)) as client:
                base = f'/api/session/{self.sid}'
                r = await client.post(base+'/interrupt',json={},headers={'Origin':'https://untrusted.example'})
                self.assertEqual(r.status,403)
                r = await client.post(base+'/permission/stale',json={'allow':'true'})
                self.assertEqual(r.status,400)
                r = await client.post(base+'/permission/stale',json={'allow':True})
                self.assertEqual(r.status,409)
                r = await client.get(base+'/preview',params={'path':'note.md'})
                self.assertEqual((await r.json())['text'],'# Safe preview')
                r = await client.get(base+'/preview',params={'path':'escape'})
                self.assertEqual(r.status,403)
                r = await client.get(base+'/preview',params={'path':'/etc/passwd'})
                self.assertEqual(r.status,403)

if __name__ == '__main__':
    unittest.main()
