// Run inside the frontend container: node < this_file
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const exportsObject = {};
const code = ts.transpileModule(fs.readFileSync('/app/lib/livenessCapture.ts', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
vm.runInNewContext(code, { exports: exportsObject });
const { captureLivenessSequence } = exportsObject;
(async () => {
  for (const action of ['blink', 'head_turn', 'smile']) {
    let now = 0, stage = 0;
    const captured = [], prompts = [];
    const frames = await captureLivenessSequence(action, {
      assertActive() {},
      wait: async ms => { now += ms; },
      prompt: (title, detail, seconds, nextStage) => { stage = nextStage; prompts.push({ title, detail, seconds, stage }); },
      capture: () => { captured.push({ stage, now }); return `frame-${now}`; },
    });
    assert.equal(now, 12000);
    assert.equal(frames.length, 15);
    assert.equal(new Set(frames).size, 15);
    assert.deepEqual(captured.map(f => f.stage), [1,1,1,1,1,2,2,2,2,2,3,3,3,3,3]);
    assert.equal(captured[0].now, 4400); // Countdown and reaction time precede recording.
    assert.equal(captured[5].now - captured[4].now, 1400);
    assert.deepEqual(prompts.slice(0, 3).map(p => p.seconds), [3,2,1]);
    assert.match(prompts.at(-1).detail, /open your eyes and relax your mouth/);
  }
  for (const stopAt of [0, 1000, 4500, 8000, 12000]) {
    let now = 0, captured = 0;
    await assert.rejects(captureLivenessSequence('blink', {
      assertActive() { if (now >= stopAt) throw new Error('interrupted or expired'); },
      wait: async ms => { now += ms; }, prompt() {},
      capture: () => { captured++; return 'frame'; },
    }), /interrupted or expired/);
    assert.ok(captured < 15, 'Interrupted/expired capture must never produce a complete submission');
  }
  console.log('PASS: all three gestures, preparation/settling times, 15 ordered frames, cancellation and expiry');
})().catch(error => { console.error(error); process.exitCode = 1; });
