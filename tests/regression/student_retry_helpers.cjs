// Run inside a frontend container: node < tests/regression/student_retry_helpers.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const root = process.env.FRONTEND_ROOT || '/app';
const exportsObject = {};
const code = ts.transpileModule(fs.readFileSync(`${root}/components/check-in/ResultStep.tsx`, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
vm.runInNewContext(code, {
  exports: exportsObject,
  require: (id) => id === './GlassCard' ? { GlassCard: ({ children }) => React.createElement('div', null, children) } : require(id),
});
const { ResultStep } = exportsObject;
const render = (status, extra = {}) => renderToStaticMarkup(React.createElement(ResultStep, {
  variant: 'SUCCESS', result: { id: 'record', status, rejection_reasons: ['The smile sequence was not detected.'] },
  errorMessage: null, onReset() {}, onRetry() {}, ...extra,
}));
const rejected = render('rejected');
assert.match(rejected, /Why it was rejected/);
assert.match(rejected, /The smile sequence was not detected/);
assert.match(rejected, /Retry attendance/);
assert.match(rejected, /Back to dashboard/);
for (const status of ['approved', 'flagged', 'pending', 'appealed']) {
  const html = render(status);
  assert.doesNotMatch(html, /Retry attendance|Why it was rejected/);
}
assert.match(render('rejected', { result: { id: 'legacy', status: 'rejected' } }), /detailed reason is unavailable/);
const error = render('rejected', { variant: 'ERROR', errorMessage: 'Attendance is closed.' });
assert.match(error, /Attendance is closed/);
assert.doesNotMatch(error, /Retry attendance|Why it was rejected/);
console.log('PASS: rejection reasons, legacy fallback, retry button, and distinct review/error states');
