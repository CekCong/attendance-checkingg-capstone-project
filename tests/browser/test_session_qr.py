"""Decode real QR pixels with jsQR; camera permission/streams and API are doubles."""
import base64
from datetime import datetime, timedelta, timezone
import io
import json
import os
import time
from urllib.parse import urlparse

import pytest
import qrcode
from playwright.sync_api import sync_playwright, expect

URL = os.getenv('TEST_FRONTEND_URL', 'http://localhost:3000')
SESSION = '77777777-7777-4777-8777-777777777777'
CODE = 'a-real-session-code-0123456789'


def qr_image(value):
    stream = io.BytesIO()
    qrcode.make(value).save(stream, format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()


@pytest.fixture
def scanner_page():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
        context = browser.new_context(viewport={'width':390,'height':844})
        page = context.new_page()
        payload = base64.urlsafe_b64encode(json.dumps({'exp':int(time.time())+3600}).encode()).decode().rstrip('=')
        now = datetime.now(timezone.utc)
        calls = []
        def handler(route):
            path = urlparse(route.request.url).path; calls.append(path)
            if path == '/api/auth/refresh':
                data = {'access_token':f'test.{payload}.signature', 'user':{'id':'student','email':'s@example.com','full_name':'Student','role':'student'}}
            elif path == '/api/v1/sessions/my-sessions':
                data = [{'id':SESSION, 'name':'QR Class','course_id':'course', 'status':'active', 'qr_code_enabled':True,
                         'checkin_opens_at':(now-timedelta(minutes=5)).isoformat(),'checkin_closes_at':(now+timedelta(hours=1)).isoformat()}]
            elif path == '/api/v1/checkins/my-checkins': data = []
            else: raise AssertionError(path)
            route.fulfill(json=data,headers={'Access-Control-Allow-Origin':'*'})
        page.route('**/api/**',handler)
        page.add_init_script('''
          window.qrStreams = [];
          window.qrSource = null;
          window.setQrImage = async function(src) {
            const img = new Image(); img.src = src; await img.decode();
            window.qrCanvas.width = img.width; window.qrCanvas.height = img.height;
            window.qrCanvas.getContext('2d').drawImage(img, 0, 0);
          };
          navigator.mediaDevices.getUserMedia = async () => {
            window.qrCanvas = document.createElement('canvas');
            window.qrCanvas.width = 640; window.qrCanvas.height = 480;
            window.qrCanvas.getContext('2d').fillRect(0, 0, 640, 480);
            if (window.qrSource) await window.setQrImage(window.qrSource);
            const stream = window.qrCanvas.captureStream(10);
            window.qrStreams.push(stream);
            if (window.delayQrPermission) await new Promise(resolve => window.resolveQrPermission = resolve);
            return stream;
          };
        ''')
        page.goto(URL)
        page.get_by_label('Session',exact=True).select_option(SESSION)
        yield page, calls
        context.close(); browser.close()


@pytest.mark.parametrize('structured', [False, True])
def test_real_qr_pixels_fill_code_stop_camera_and_preserve_consent(scanner_page, structured):
    page,calls = scanner_page
    value = json.dumps({'v':1,'session_id':SESSION,'code':CODE}) if structured else CODE
    page.evaluate('(src) => window.qrSource = src',qr_image(value))
    page.get_by_role('button', name='Scan session QR code').click()
    expect(page.get_by_label('Session verification code',exact=True)).to_have_value(CODE)
    page.wait_for_function('window.qrStreams.length === 1 && window.qrStreams.every(s => s.getTracks().every(t => t.readyState === "ended"))')
    assert '/api/v1/checkins/' not in calls
    assert 'data:image' not in page.evaluate('JSON.stringify({...localStorage, ...sessionStorage})')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.get_by_role('button',name='Continue to verification').click()
    expect(page.get_by_role('button', name='I agree — continue')).to_be_disabled()


@pytest.mark.parametrize('value,message', [
    ('https://untrusted.example/attendance?token=secret', 'This is not a session verification code.'),
    (json.dumps({'v':1,'session_id':'other','code':CODE}), 'This QR code is for a different session.')])
def test_wrong_session_or_url_is_rejected_without_navigation(scanner_page, value, message):
    page,calls = scanner_page
    page.evaluate('(src) => window.qrSource = src',qr_image(value))
    page.get_by_role('button',name='Scan session QR code').click()
    expect(page.get_by_role('status')).to_contain_text(message)
    expect(page.get_by_label('Session verification code',exact=True)).to_have_value('')
    assert page.url.startswith(URL)
    page.get_by_role('button',name='Close scanner').click()
    page.wait_for_function('window.qrStreams.every(s => s.getTracks().every(t => t.readyState === "ended"))')
    page.get_by_label('Session verification code',exact=True).fill(CODE)
    expect(page.get_by_role('button',name='Continue to verification')).to_be_enabled()


def test_permission_denial_keeps_manual_entry_available(scanner_page):
    page,_ = scanner_page
    page.evaluate("() => { navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('Denied', 'NotAllowedError'); }; }")
    page.get_by_role('button',name='Scan session QR code').click()
    expect(page.get_by_role('status')).to_contain_text('permission denied')
    page.get_by_role('button',name='Close scanner').click()
    page.get_by_label('Session verification code',exact=True).fill(CODE)
    expect(page.get_by_role('button',name='Continue to verification')).to_be_enabled()


def test_cancel_before_permission_resolves_releases_late_stream(scanner_page):
    page,_ = scanner_page
    page.evaluate('window.delayQrPermission = true')
    page.get_by_role('button',name='Scan session QR code').click()
    page.wait_for_function('typeof window.resolveQrPermission === "function"')
    page.get_by_role('button',name='Close scanner').click()
    page.evaluate('window.resolveQrPermission()')
    page.wait_for_function('window.qrStreams.every(s => s.getTracks().every(t => t.readyState === "ended"))')
    expect(page.get_by_label('Session verification code',exact=True)).to_have_value('')


def test_instructor_issues_decodable_qr_and_hides_expired_code():
    import cv2
    import numpy as np
    url = os.getenv('TEST_DASHBOARD_URL','http://localhost:8501')
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        page = browser.new_page(viewport={'width':390,'height':844})
        issued = []
        now = datetime.now(timezone.utc)
        token = base64.urlsafe_b64encode(json.dumps({'exp':int(time.time())+3600}).encode()).decode().rstrip('=')
        def handler(route):
            path = urlparse(route.request.url).path
            if path == '/api/auth/refresh':
                data = {'access_token':f'test.{token}.sig','user':{'id':'teacher','email':'t@example.com','full_name':'Teacher','role':'instructor'}}
            elif path == f'/api/v1/sessions/{SESSION}/qr-code':
                assert route.request.method == 'POST'
                code = CODE + str(len(issued))
                data = {'code':code,'payload':json.dumps({'v':1,'session_id':SESSION,'code':code}),
                        'expires_at':(datetime.now(timezone.utc)+timedelta(seconds=2 if issued else 90)).isoformat()}
                issued.append(data)
            else:
                if path == '/api/v1/sessions/':
                    rows = [{'id':SESSION,'course_id':'course','course_code':'QR101','course_name':'QR Class','name':'QR Class','status':'active',
                             'scheduled_start':now.isoformat(),'scheduled_end':(now+timedelta(hours=1)).isoformat(),
                             'checkin_opens_at':now.isoformat(),'checkin_closes_at':(now+timedelta(hours=1)).isoformat(),'total_enrolled':1,'checked_in_count':0}]
                elif path == '/api/v1/courses/': rows = [{'id':'course','code':'QR101','name':'QR Class','semester':'2026'}]
                elif path in ['/api/v1/checkins/','/api/v1/checkins/flagged','/api/v1/audit/logs']: rows = []
                else: raise AssertionError(path)
                data = {'items':rows,'total':len(rows),'limit':100,'offset':0}
            route.fulfill(json=data,headers={'Access-Control-Allow-Origin':'*'})
        page.route('**/api/**',handler)
        try:
            page.goto(url)
            page.get_by_role('button',name='Issue / rotate session QR').click()
            image = page.get_by_alt_text('Session verification QR code')
            expect(image).to_be_visible()
            encoded = image.get_attribute('src').split(',')[1]
            pixels = cv2.imdecode(np.frombuffer(base64.b64decode(encoded),np.uint8),cv2.IMREAD_COLOR)
            decoded,_,_ = cv2.QRCodeDetector().detectAndDecode(pixels)
            assert json.loads(decoded) == {'v':1,'session_id':SESSION,'code':issued[0]['code']}
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.get_by_role('button',name='Issue / rotate session QR').click()
            expect(page.get_by_text('Manual code:',exact=False)).to_contain_text(CODE+'1')
            expect(page.get_by_role('status')).to_contain_text('QR code expired',timeout=6000)
            expect(image).to_have_count(0)
        finally: browser.close()
