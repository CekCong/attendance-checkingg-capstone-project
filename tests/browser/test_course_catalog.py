"""Instructor catalog selection UI, with explicit HTTP test doubles."""
import base64
import json
import os
import time
from urllib.parse import urlparse

import pytest
from playwright.sync_api import sync_playwright, expect


@pytest.fixture
def catalog_page():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH', '/usr/bin/chromium'), args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        token = base64.urlsafe_b64encode(json.dumps({'exp': int(time.time()) + 3600}).encode()).decode().rstrip('=')
        course = {'id': 'catalog-course', 'code': 'CAT101', 'name': 'Catalog Course', 'semester': '2026-S1'}
        state = {'available': [course], 'owned': [], 'assignments': [], 'conflict': False, 'fail_load': False}

        def handler(route):
            path = urlparse(route.request.url).path
            cors = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*'}
            if route.request.method == 'OPTIONS':
                route.fulfill(status=204, headers=cors); return
            if path == '/api/auth/refresh':
                data = {'access_token': f'test.{token}.sig', 'user': {'id': 'teacher', 'email': 'teacher@example.com', 'full_name': 'Teacher', 'role': 'instructor'}}
            elif path == '/api/v1/courses/catalog-course/assignment':
                assert route.request.method == 'POST'
                state['assignments'].append(path)
                if state['conflict']:
                    route.fulfill(status=409, json={'detail': 'This course is already assigned to another instructor. Refresh the available courses.'}, headers=cors); return
                state['owned'] = [course]; state['available'] = []
                data = course
            elif path == '/api/v1/enrollments/course/catalog-course/roster':
                data = {'items': []}
            else:
                assert route.request.method == 'GET', 'Catalog selection must never create a course'
                if path == '/api/v1/courses/available':
                    if state['fail_load']:
                        route.fulfill(status=503, json={'detail': 'Catalog temporarily unavailable.'}, headers=cors); return
                    rows = state['available']
                elif path == '/api/v1/courses/': rows = state['owned']
                elif path in ('/api/v1/sessions/', '/api/v1/checkins/', '/api/v1/checkins/flagged', '/api/v1/audit/logs'): rows = []
                else: raise AssertionError(path)
                data = {'items': rows, 'total': len(rows), 'offset': 0, 'limit': 100}
            route.fulfill(json=data, headers=cors)

        page.route('**/api/**', handler)
        page.goto(os.getenv('TEST_DASHBOARD_URL', 'http://localhost:8501'))
        page.get_by_text('Courses, students & semesters', exact=True).click()
        yield page, state
        browser.close()


def test_add_existing_course_selects_it_without_creation_fields(catalog_page):
    page, state = catalog_page
    page.get_by_role('button', name='Add existing course', exact=True).click()
    expect(page.get_by_label('Course code', exact=True)).to_have_count(0)
    expect(page.get_by_label('Course name', exact=True)).to_have_count(0)
    button = page.get_by_role('button', name='Add to my courses', exact=True)
    expect(button).to_be_disabled()
    page.get_by_role('combobox', name='Available course', exact=True).select_option('catalog-course')
    button.click()
    expect(page.get_by_text('CAT101 added and selected.', exact=False)).to_be_visible()
    expect(page.get_by_role('combobox', name='Course for new sessions', exact=True)).to_have_value('catalog-course')
    assert len(state['assignments']) == 1
    page.reload()
    page.get_by_text('Courses, students & semesters', exact=True).click()
    expect(page.get_by_role('combobox', name='Course for new sessions', exact=True).locator('option[value="catalog-course"]')).to_have_count(1)


def test_empty_catalog_explains_next_step(catalog_page):
    page, state = catalog_page
    state['available'] = []
    page.get_by_role('button', name='Add existing course', exact=True).click()
    expect(page.get_by_text('No unassigned courses are available.', exact=False)).to_be_visible()
    expect(page.get_by_role('button', name='Add to my courses', exact=True)).to_be_disabled()
    assert not state['assignments']


def test_assignment_conflict_can_refresh_catalog(catalog_page):
    page, state = catalog_page
    state['conflict'] = True
    page.get_by_role('button', name='Add existing course', exact=True).click()
    page.get_by_role('combobox', name='Available course', exact=True).select_option('catalog-course')
    page.get_by_role('button', name='Add to my courses', exact=True).click()
    expect(page.get_by_role('alert').filter(has_text='already assigned')).to_be_visible()
    assert not state['owned']
    state['available'] = []
    page.get_by_role('button', name='Refresh available courses', exact=True).click()
    expect(page.get_by_text('No unassigned courses are available.', exact=False)).to_be_visible()


def test_catalog_load_failure_can_retry(catalog_page):
    page, state = catalog_page
    state['fail_load'] = True
    page.get_by_role('button', name='Add existing course', exact=True).click()
    expect(page.get_by_role('alert').filter(has_text='Catalog temporarily unavailable.')).to_be_visible()
    expect(page.get_by_role('button', name='Add to my courses', exact=True)).to_be_disabled()
    state['fail_load'] = False
    page.get_by_role('button', name='Refresh available courses', exact=True).click()
    expect(page.get_by_role('combobox', name='Available course', exact=True)).to_be_visible()
