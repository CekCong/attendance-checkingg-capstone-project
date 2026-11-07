// Run inside a frontend container: node < tests/regression/student_join_helpers.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const root = process.env.FRONTEND_ROOT || '/app';

function load(path, overrides = {}) {
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(`${root}/${path}`, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  vm.runInNewContext(code, { exports, URL, URLSearchParams, Date,
    require: (id) => overrides[id] || require(id),
  });
  return exports;
}

const { readSessionQr } = load('lib/sessionQr.ts');
assert.equal(readSessionQr('ABCD2345'), 'ABCD2345');
assert.equal(readSessionQr('https://students.example.edu/#attendance=ABCD2345'), 'ABCD2345');
assert.equal(readSessionQr(JSON.stringify({ v: 1, session_id: 'lesson', code: 'ABCD2345' })), 'ABCD2345');
assert.throws(() => readSessionQr('https://example.edu/?token=ABCD2345'));
assert.throws(() => readSessionQr('javascript:alert(1)'));
assert.throws(() => readSessionQr(JSON.stringify({ v: 2, session_id: 'lesson', code: 'ABCD2345' })));
assert.throws(() => readSessionQr('x'.repeat(513)));
assert.throws(() => readSessionQr(JSON.stringify({ v: 1, session_id: 'other', code: 'ABCD2345' }), 'lesson'));

const { StudentDashboard } = load('components/dashboards/StudentDashboard.tsx', {
  '@/components/auth/AuthProvider': { useAuth: () => ({ user: { matriculation_number: 'U1234567A' } }) },
  '@/components/check-in/SessionQrScanner': { SessionQrScanner: () => null },
  '@/components/check-in/GlassCard': { GlassCard: ({ children }) => React.createElement('div', null, children) },
  '@/lib/studentApi': { serverTime: Date.parse },
  'next/link': ({ children }) => React.createElement('a', null, children),
});
const html = renderToStaticMarkup(React.createElement(StudentDashboard, { token: 'test', onStartCheckIn() {} }));
assert.equal((html.match(/<input\b/g) || []).length, 1);
assert.match(html, /Attendance passcode/);
assert.match(html, /Join with passcode/);
assert.match(html, /Scan QR code/);
assert.match(html, /Attendance history/);
assert.doesNotMatch(html, /<select\b|Session verification code|Continue to verification/);
console.log('PASS: single passcode input, standalone QR action, retained history, and safe QR parsing');
