// Run from module1-frontend with NODE_PATH=./node_modules node ../tests/regression/student_proxy_helpers.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
const exportsObject = {};
let calls = [];
let upstreamStatus = 200;
const code = ts.transpileModule(fs.readFileSync('app/api/student/[...path]/route.ts', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
vm.runInNewContext(code, {
  exports: exportsObject, Response, URL, AbortSignal,
  require: (id) => id === '@/lib/authBackend' ? { AUTH_BACKEND_URL: 'http://backend:8000' } : require(id),
  fetch: async (url, options) => {
    calls.push({ url, options });
    return new Response(upstreamStatus === 204 ? null : JSON.stringify({ status: 'from-backend' }), { status: upstreamStatus });
  },
});
async function send(method, path, authenticated = true, body) {
  const request = new Request('https://students.example.edu/api/student/' + path, {
    method, headers: authenticated ? { Authorization: 'Bearer test-token' } : {},
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const segments = new URL(request.url).pathname.replace('/api/student/', '').replace(/\/$/, '').split('/');
  return exportsObject[method](request, { params: Promise.resolve({ path: segments }) });
}
(async () => {
  assert.equal((await send('POST', 'attendance/resolve', true, { code: 'ABCD2345' })).status, 200);
  assert.equal(calls.at(-1).url, 'http://backend:8000/api/v1/attendance/resolve');
  assert.equal(calls.at(-1).options.headers.Authorization, 'Bearer test-token');
  assert.equal(JSON.parse(calls.at(-1).options.body).code, 'ABCD2345');
  const response = await send('GET', 'sessions/my-sessions?status=active&limit=100');
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.equal(calls.at(-1).url, 'http://backend:8000/api/v1/sessions/my-sessions?status=active&limit=100');
  assert.equal((await send('GET', 'enrollments/my-enrollments')).status, 200);
  assert.equal(calls.at(-1).url, 'http://backend:8000/api/v1/enrollments/my-enrollments');
  const count = calls.length;
  assert.equal((await send('POST', 'attendance/resolve', false)).status, 401);
  assert.equal((await send('POST', 'admin/users/bulk')).status, 404);
  assert.equal(calls.length, count);
  upstreamStatus = 403;
  assert.equal((await send('POST', 'checkins/', true, { session_id: 'lesson' })).status, 403);
  upstreamStatus = 204;
  assert.equal((await send('DELETE', 'devices/device-id')).status, 204);
  console.log('PASS: phone proxy authentication, code resolution, query forwarding, route boundaries, and backend status handling');
})().catch((error) => { console.error(error); process.exitCode = 1; });
