"""Production offline behavior and instructor pagination/export UI contracts."""
import base64
import json
import os
import time
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright, expect


def test_offline_shell_excludes_private_data_and_submissions():
    url = os.getenv('TEST_FRONTEND_URL', 'http://localhost:3000')
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
        context = browser.new_context(viewport={'width':390,'height':844})
        page = context.new_page()
        try:
            page.goto(url)
            page.evaluate('navigator.serviceWorker.ready')
            page.wait_for_function('navigator.serviceWorker.controller !== null')
            page.evaluate("fetch('/api/auth/refresh', {method:'POST'})")
            page.reload()
            cached = page.evaluate('''async () => (await Promise.all((await caches.keys()).map(async name =>
              (await (await caches.open(name)).keys()).map(r => new URL(r.url).pathname)))).flat()''')
            assert '/offline.html' in cached
            assert all(path.startswith('/_next/static/') or path in ('/offline.html','/manifest.json','/icon-192.png','/icon-512.png') for path in cached)
            context.set_offline(True)
            page.goto(url + '/profile')
            expect(page.get_by_role('heading', name="You're offline")).to_be_visible()
            expect(page.get_by_text('No check-in has been queued.', exact=False)).to_be_visible()
            assert page.evaluate("fetch('/api/auth/refresh', {method:'POST'}).then(() => false).catch(() => true)")
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            context.set_offline(False)
            page.get_by_role('link', name='Try again').click()
            expect(page.get_by_role('button', name='Sign in', exact=True)).to_be_visible()
        finally:
            browser.close()


def test_instructor_loads_later_pages_and_exports_from_server(tmp_path):
    url = os.getenv('TEST_DASHBOARD_URL', 'http://localhost:8501')
    now = datetime.now(timezone.utc).isoformat()
    payload = base64.urlsafe_b64encode(json.dumps({'exp': int(time.time())+3600}).encode()).decode().rstrip('=')
    calls = []
    records = [{'id':f'r-{i}', 'session_id':f's-{i}', 'session_name':f'Lecture {i}', 'student_id':f'u-{i}',
                'student_name':f'Student {i}', 'student_email':f'student{i}@example.com', 'status':'approved', 'checked_in_at':now,'risk_score':0.1} for i in range(105)]
    session_rows = [{'id':f's-{i}', 'course_id':f'c-{i}', 'course_code':f'C{i}', 'course_name':f'Course {i}',
                     'name':f'Lecture {i}', 'status':'closed', 'scheduled_start':now,'scheduled_end':now,
                     'checkin_opens_at':now,'checkin_closes_at':now,'total_enrolled':1,'checked_in_count':1} for i in range(105)]
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
        page = browser.new_page(viewport={'width':390,'height':844}, accept_downloads=True)
        def handler(route):
            parsed = urlparse(route.request.url); params = parse_qs(parsed.query)
            calls.append((parsed.path, params))
            if route.request.method == 'OPTIONS':
                route.fulfill(status=204, headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*','Access-Control-Allow-Methods':'*'}); return
            if parsed.path == '/api/auth/refresh':
                data = {'access_token':f'test.{payload}.signature', 'user':{'id':'teacher','email':'teacher@example.com','full_name':'Teacher','role':'instructor'}}
            elif parsed.path == '/api/v1/export/checkins':
                selected = params.get('session_id', [None])[0]
                rows = records if selected is None else [row for row in records if row['session_id']==selected]
                data = {'total':len(rows),'records':rows}
            else:
                if parsed.path == '/api/v1/sessions/': rows = session_rows
                elif parsed.path == '/api/v1/courses/': rows = [{'id':f'c-{i}','code':f'C{i}','name':f'Course {i}','semester':'2026'} for i in range(105)]
                elif parsed.path == '/api/v1/checkins/':
                    selected = params.get('session_id',[None])[0]
                    rows = records if selected is None else [row for row in records if row['session_id']==selected]
                elif parsed.path in ('/api/v1/checkins/flagged','/api/v1/audit/logs'): rows = []
                else: raise AssertionError(parsed.path)
                offset = int(params.get('offset',['0'])[0]); limit = int(params.get('limit',['100'])[0])
                data = {'items':rows[offset:offset+limit], 'total':len(rows),'offset':offset,'limit':limit}
            route.fulfill(json=data,headers={'Access-Control-Allow-Origin':'*'})
        page.route('**/api/**', handler)
        try:
            page.goto(url)
            expect(page.get_by_role('heading', name="Today's operations")).to_be_visible()
            page.get_by_text('Attendance records & export', exact=True).click()
            selector = page.get_by_label('Attendance session', exact=True)
            expect(selector.locator('option')).to_have_count(106)
            with page.expect_download() as download:
                page.get_by_role('button', name='Export JSON', exact=True).click()
            path = tmp_path / 'all.json'; download.value.save_as(path)
            assert json.loads(path.read_text())['total'] == 105
            selector.select_option('s-104')
            page.get_by_role('button', name='Preview table').click()
            expect(page.get_by_role('cell', name='Student 104 student104@example.com', exact=True)).to_be_visible()
            with page.expect_download() as download:
                page.get_by_role('button', name='Export JSON', exact=True).click()
            path = tmp_path / 'session.json'; download.value.save_as(path)
            assert json.loads(path.read_text())['total'] == 1
            assert any(path == '/api/v1/checkins/' and params.get('offset') == ['100'] for path, params in calls)
            assert any(path == '/api/v1/export/checkins' and params.get('session_id') == ['s-104'] for path, params in calls)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        finally:
            browser.close()
