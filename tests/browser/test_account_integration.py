"""Browser account flow against the real Next.js and backend services."""
import os
import uuid
import httpx
from playwright.sync_api import sync_playwright, expect


def test_registration_profile_and_password_persist():
    frontend = os.getenv('TEST_FRONTEND_URL', 'http://localhost:3000')
    backend = os.getenv('TEST_BACKEND_URL', 'http://localhost:8020')
    email = f'browser-{uuid.uuid4().hex}@example.com'
    password = 'browser-original-password'
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH', '/usr/bin/chromium'), args=['--no-sandbox'])
        page = browser.new_page()
        try:
            page.goto(frontend)
            page.get_by_role('button', name='Create a student account').click()
            page.get_by_label('Full name', exact=True).fill('Browser Account')
            page.get_by_label('Email', exact=True).fill(email)
            page.get_by_label('Password', exact=True).fill(password)
            page.get_by_role('button', name='Create account', exact=True).click()
            expect(page.get_by_role('heading', name='Join a class')).to_be_visible(timeout=20000)
            page.get_by_role('link', name='Profile', exact=True).click()
            page.get_by_label('Display name', exact=True).fill('Persisted Name')
            page.get_by_role('button', name='Save profile').click()
            expect(page.get_by_text('Profile saved.', exact=False)).to_be_visible()
            page.reload()
            expect(page.get_by_label('Display name', exact=True)).to_have_value('Persisted Name')
            page.get_by_label('Current password', exact=True).fill('incorrect-password')
            page.get_by_label('New password', exact=True).fill('browser-updated-password')
            page.get_by_label('Confirm new password', exact=True).fill('browser-updated-password')
            page.get_by_role('button', name='Update password').click()
            expect(page.get_by_text('Current password is incorrect', exact=True)).to_be_visible()
            page.get_by_label('Current password', exact=True).fill(password)
            page.get_by_role('button', name='Update password').click()
            # Password changes now revoke all sessions, including this browser.
            expect(page.get_by_label('Password', exact=True)).to_be_visible()
            assert page.evaluate("sessionStorage.getItem('saiv_access_token')") is None
            with httpx.Client(base_url=backend) as api:
                assert api.post('/api/v1/auth/login', json={'email': email, 'password': password}).status_code == 401
                logged_in = api.post('/api/v1/auth/login', json={'email': email, 'password': 'browser-updated-password'})
                assert logged_in.status_code == 200
                assert logged_in.json()['user']['full_name'] == 'Persisted Name'
            page.get_by_label('Email', exact=True).fill(email)
            page.get_by_label('Password', exact=True).fill('browser-updated-password')
            page.get_by_role('button', name='Sign in', exact=True).click()
            expect(page.get_by_label('Display name', exact=True)).to_have_value('Persisted Name')
            deletion = page.get_by_role('button', name='Schedule account deletion')
            expect(deletion).to_be_disabled()
            page.get_by_label('Password to confirm deletion').fill('browser-updated-password')
            page.get_by_label('I understand that my account will be disabled and my data erased.').check()
            deletion.click()
            expect(page.get_by_label('Password', exact=True)).to_be_visible()
            with httpx.Client(base_url=backend) as api:
                assert api.post('/api/v1/auth/login', json={'email': email, 'password': 'browser-updated-password'}).status_code == 403
        finally:
            browser.close()
