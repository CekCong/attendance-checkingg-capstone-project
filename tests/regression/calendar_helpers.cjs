// Run inside the frontend container: node < tests/regression/calendar_helpers.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
function load(file, extra = {}) {
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  vm.runInNewContext(code, { exports, require, Date, Intl, URLSearchParams, AbortSignal, process, ...extra });
  return exports;
}
const root = process.env.FRONTEND_ROOT || '/app';
const c = load(`${root}/lib/calendar.ts`);
assert.equal(c.singaporeDate(new Date('2026-10-29T17:00:00Z')), '2026-10-30');
assert.equal(c.localInstant('2026-11-02', '07:30'), '2026-11-01T23:30:00.000Z');
assert.equal(c.weekStart('2026-11-01'), '2026-10-26');
assert.equal(c.addDays('2026-12-31', 1), '2027-01-01');
assert.equal(c.parseSessionDate('2026-11-01T23:30:00').toISOString(), '2026-11-01T23:30:00.000Z');
assert.equal(JSON.stringify(c.recurringDates('2026-11-01', '2026-11-16', 0)), JSON.stringify(['2026-11-02', '2026-11-09', '2026-11-16']));
assert.equal(c.recurringDates('2026-11-02', '2026-11-02', 1).length, 0);
assert.ok(c.semesterOptions('2026-10-30').some((item) => item.value === '2026/27 Semester 1'));
assert.ok(c.semesterOptions('2026-10-30').every((item) => item.value.length <= 20));
const event = (id, start, end) => ({ id, scheduled_start: start, scheduled_end: end });
const layout = c.layoutDay([
  event('a', '2026-11-02T09:00:00+08:00', '2026-11-02T10:00:00+08:00'),
  event('b', '2026-11-02T09:30:00+08:00', '2026-11-02T11:00:00+08:00'),
  event('c', '2026-11-02T11:00:00+08:00', '2026-11-02T12:00:00+08:00'),
  event('overnight', '2026-11-01T23:00:00+08:00', '2026-11-02T01:00:00+08:00'),
  event('tomorrow', '2026-11-03T09:00:00+08:00', '2026-11-03T10:00:00+08:00'),
], '2026-11-02');
assert.equal(layout.length, 4);
assert.equal(layout.find((item) => item.event.id === 'a').columns, 2);
assert.equal(layout.find((item) => item.event.id === 'b').column, 1);
assert.equal(layout.find((item) => item.event.id === 'c').columns, 1);
assert.equal(layout.find((item) => item.event.id === 'overnight').start, 0);
assert.equal(layout.find((item) => item.event.id === 'overnight').end, 60);
(async () => {
  let calls = 0;
  const api = load(`${root}/lib/instructorApi.ts`, { require: (id) => id === '@/lib/calendar' ? c : require(id), fetch: async (url) => {
    calls++;
    const offset = Number(new URL(url).searchParams.get('offset'));
    return { ok: true, json: async () => ({ total: 105, items: Array.from({length: Math.min(100, 105-offset)}, (_, i) => ({id: offset+i})) }) };
  }});
  const result = await api.fetchSessions('test', { start: '2026-11-01T00:00:00Z', end: '2026-12-01T00:00:00Z' });
  assert.equal(result.length, 105);
  assert.equal(calls, 2);
  console.log('PASS: Singapore time, inclusive recurrence, semester choices, overlaps, midnight clipping, and >100-session pagination');
})().catch((error) => { console.error(error); process.exitCode = 1; });
assert.equal(c.monthDays('2026-11-12').length, 42);
assert.equal(c.monthDays('2026-11-12')[0], '2026-10-26');
assert.equal(c.monthDays('2026-11-12')[41], '2026-12-06');
assert.equal(c.addMonths('2026-01-31', 1), '2026-02-01');
assert.equal(c.addMonths('2026-12-30', 1), '2027-01-01');
console.log('PASS: month grid, year boundaries, and month navigation');
