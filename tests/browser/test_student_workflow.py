"""UI contracts with browser camera capture and explicit API test doubles.

These tests verify orchestration and permissions, not biometric accuracy.
Run with a Next server at TEST_FRONTEND_URL and Chromium installed.
"""
import base64
import json
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from playwright.sync_api import sync_playwright, expect

URL = os.getenv('TEST_FRONTEND_URL', 'http://localhost:3000')
USER = {'id': 'student-browser', 'email': 'browser@example.com', 'full_name': 'Browser Student', 'role': 'student'}


@pytest.fixture
def browser():
    with sync_playwright() as p:
        instance = p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH', '/usr/bin/chromium'),
                                    args=['--no-sandbox', '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'])
        yield instance
        instance.close()


def setup_page(browser, status='approved', camera_denied=False, location_denied=False, fail_submission=False):
    mobile = {'viewport': {'width': 390, 'height': 844}, 'is_mobile': True} if os.getenv('TEST_MOBILE') else {}
    context = browser.new_context(permissions=['camera', 'geolocation'], geolocation={'latitude': 1.3483, 'longitude': 103.6831, 'accuracy': 20}, **mobile)
    page = context.new_page()
    page.add_init_script('''
      window.testStreams = [];
      const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
      navigator.mediaDevices.getUserMedia = async (...args) => {
        const stream = await original(...args); window.testStreams.push(stream); return stream;
      };
    ''')
    if camera_denied:
        page.add_init_script("navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('Denied', 'NotAllowedError'); };")
    if location_denied:
        page.add_init_script("navigator.geolocation.getCurrentPosition = (ok, fail) => fail({code:1, PERMISSION_DENIED:1});")
    state = {'consent': None, 'enrolled': False, 'submissions': [], 'public_key': None, 'challenge': 'browser-device-nonce',
             'readiness': {'ready': True, 'message': 'Ready', 'warnings': []}}
    payload = base64.urlsafe_b64encode(json.dumps({'exp': int(time.time()) + 3600}).encode()).decode().rstrip('=')
    token = f'test.{payload}.signature'
    now = datetime.now(timezone.utc)
    session = {'id': 'session-browser', 'course_id': 'course-browser', 'name': 'Real API Session', 'status': 'active',
               'checkin_opens_at': (now - timedelta(minutes=5)).isoformat(), 'checkin_closes_at': (now + timedelta(hours=1)).isoformat(), 'qr_code_enabled': False}
    def handler(route):
        path = urlparse(route.request.url).path.replace('/api/student/', '/api/v1/')
        body = route.request.post_data_json if route.request.method in ('POST','PUT') else None
        data = {}
        if path == '/api/auth/refresh': data = {'access_token': token, 'user': USER}
        elif path == '/api/v1/sessions/my-sessions': data = [session]
        elif path == '/api/v1/enrollments/my-enrollments': data = []
        elif path == '/api/v1/attendance/resolve':
            assert body['code'] == 'ABCD2345'
            data = {'session_id': session['id'], 'qr_code': 'ABCD2345'}
        elif path == '/api/v1/sessions/session-browser': data = session
        elif path == '/api/v1/checkins/my-checkins':
            data = [] if not state['submissions'] else [{'id':'record-browser', 'session_name':session['name'], 'course_code':'REAL101', 'status':status, 'checked_in_at':now.isoformat()}]
        elif path == '/api/v1/users/me':
            state['consent'] = body
            data = {**USER, 'face_enrolled': state['enrolled']}
        elif path == '/api/v1/devices/my-devices': data = []
        elif path == '/api/v1/devices/register':
            state['public_key'] = body['public_key']
            data = {'id':'device-browser'}
        elif path == '/api/v1/users/me/face/readiness':
            assert state['consent']['camera_consent']
            data = state['readiness']
        elif path == '/api/v1/users/me/face/enroll':
            assert state['consent'] == {'camera_consent': True, 'geolocation_consent': True}
            assert base64.b64decode(body['image']).startswith(b'\xff\xd8')
            state['enrolled'] = True
            data = {'success': True, 'face_enrolled': True}
        elif path == '/api/v1/checkins/liveness-challenge':
            assert state['enrolled']
            data = {'challenge_id':'ticket-browser', 'challenge_type':'blink', 'expires_in':60}
        elif path == '/api/v1/devices/challenge': data = {'challenge':state['challenge'], 'expires_in':120}
        elif path == '/api/v1/checkins/':
            if fail_submission:
                route.abort('failed')
                return
            state['submissions'].append(body)
            data = {'id':'record-browser', 'status':status}
        else: raise AssertionError(f'Unexpected request: {route.request.method} {path}')
        route.fulfill(json=data, headers={'Access-Control-Allow-Origin':'*'})
    page.route('**/api/**', handler)
    page.goto(URL)
    expect(page.get_by_role('heading', name='Join a class')).to_be_visible()
    expect(page.get_by_label('Session', exact=True)).to_have_count(0)
    expect(page.get_by_label('Session verification code', exact=True)).to_have_count(0)
    page.get_by_label('Attendance passcode', exact=True).fill('ABCD2345')
    page.get_by_role('button', name='Join with passcode').click()
    return context, page, state


def consent_and_enroll(page):
    button = page.get_by_role('button', name='I agree — continue')
    expect(button).to_be_disabled()
    page.get_by_role('checkbox').nth(0).check()
    expect(button).to_be_disabled()
    page.get_by_role('checkbox').nth(1).check()
    button.click()
    expect(page.get_by_role('heading', name='Enroll your face')).to_be_visible()
    page.get_by_role('button', name='Check camera & capture photo').click()


@pytest.mark.parametrize('status,title', [('approved','Attendance approved'), ('flagged','Check-in needs review'), ('rejected','Check-in rejected')])
def test_live_capture_submission_and_actual_status(browser, status, title):
    context, page, state = setup_page(browser, status)
    try:
        consent_and_enroll(page)
        page.get_by_role('button', name='Check camera & start challenge').click()
        expect(page.get_by_role('heading', name=title)).to_be_visible(timeout=20000)
        assert len(state['submissions']) == 1
        body = state['submissions'][0]
        assert len(body['liveness_challenge_response']) == 15
        assert all(base64.b64decode(frame.split(',')[1]).startswith(b'\xff\xd8') for frame in body['liveness_challenge_response'])
        assert body['liveness_challenge_id'] == 'ticket-browser'
        assert body['liveness_challenge_type'] == 'blink'
        assert body['latitude'] == pytest.approx(1.3483)
        public = serialization.load_pem_public_key(state['public_key'].encode())
        public.verify(base64.b64decode(body['device_signature']), state['challenge'].encode(), padding.PSS(mgf=padding.MGF1(hashes.SHA256()),salt_length=32), hashes.SHA256())
        assert page.evaluate('window.testStreams.every(s => s.getTracks().every(t => t.readyState === "ended"))')
        assert 'data:image' not in page.evaluate('JSON.stringify({...localStorage, ...sessionStorage})')
        page.get_by_role('button', name='Back to dashboard').click()
        expect(page.get_by_text(status, exact=True)).to_be_visible()
    finally: context.close()


def test_camera_denial_does_not_submit(browser):
    context, page, state = setup_page(browser, camera_denied=True)
    try:
        page.get_by_role('checkbox').nth(0).check()
        page.get_by_role('checkbox').nth(1).check()
        page.get_by_role('button', name='I agree — continue').click()
        expect(page.get_by_text('Camera unavailable or permission denied.', exact=False)).to_be_visible()
        assert not state['submissions']
    finally: context.close()


def test_location_denial_releases_camera_and_does_not_submit(browser):
    context, page, state = setup_page(browser, location_denied=True)
    try:
        consent_and_enroll(page)
        expect(page.get_by_text('Location permission was denied', exact=False)).to_be_visible()
        assert not state['submissions']
        assert page.evaluate('window.testStreams.every(s => s.getTracks().every(t => t.readyState === "ended"))')
    finally: context.close()


def test_cancel_stops_camera(browser):
    context, page, state = setup_page(browser)
    try:
        page.get_by_role('checkbox').nth(0).check()
        page.get_by_role('checkbox').nth(1).check()
        page.get_by_role('button', name='I agree — continue').click()
        expect(page.get_by_role('button', name='Check camera & capture photo')).to_be_enabled()
        page.get_by_role('button', name='Cancel verification').click()
        expect(page.get_by_role('heading', name='Join a class')).to_be_visible()
        assert page.evaluate('window.testStreams.every(s => s.getTracks().every(t => t.readyState === "ended"))')
        assert not state['submissions']
    finally: context.close()


def test_camera_preparation_failure_can_retry_without_restarting(browser):
    context, page, state = setup_page(browser)
    try:
        state['readiness'] = {'ready': False, 'message': 'Move closer and face the camera.', 'warnings': []}
        consent_and_enroll(page)
        expect(page.get_by_role('alert').filter(has_text='Move closer')).to_be_visible()
        assert not state['enrolled'] and not state['submissions']
        assert page.evaluate('window.testStreams.some(s => s.getVideoTracks().some(t => t.readyState === "live"))')
        state['readiness'] = {'ready': True, 'message': 'Ready', 'warnings': []}
        page.get_by_role('button', name='Check camera & capture photo').click()
        expect(page.get_by_role('heading', name='Liveness challenge')).to_be_visible(timeout=10000)
        assert state['enrolled']
    finally: context.close()


def test_cancel_during_countdown_does_not_submit(browser):
    context, page, state = setup_page(browser)
    try:
        consent_and_enroll(page)
        page.get_by_role('button', name='Check camera & start challenge').click()
        expect(page.get_by_text('Get ready — start with a neutral face', exact=True)).to_be_visible()
        page.get_by_role('button', name='Cancel verification').click()
        expect(page.get_by_role('heading', name='Join a class')).to_be_visible()
        page.wait_for_timeout(13000)
        assert not state['submissions']
        assert page.evaluate('window.testStreams.every(s => s.getTracks().every(t => t.readyState === "ended"))')
    finally: context.close()


def test_network_failure_does_not_report_success(browser):
    context, page, state = setup_page(browser, fail_submission=True)
    try:
        consent_and_enroll(page)
        page.get_by_role('button', name='Check camera & start challenge').click()
        expect(page.get_by_role('heading', name='Check-in could not be completed')).to_be_visible(timeout=20000)
        expect(page.get_by_text('Cannot reach the server.', exact=False)).to_be_visible()
        assert not state['submissions']
        assert page.evaluate('window.testStreams.every(s => s.getTracks().every(t => t.readyState === "ended"))')
    finally: context.close()
