'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const os = require('node:os');
const path = require('node:path');
const fs = require('node:fs/promises');
const {spawnSync} = require('node:child_process');
const {configuration, compileArguments, testRunner} = require('../src/core');
const {execute} = require('../src/runner');
const manifest = require('../package.json');

test('compiler invocation keeps paths and program arguments as individual arguments', () => {
  const config = configuration({compilerPath: './tool chain/tinc', toolchainRoot: './tool chain', entryFiles: ['a b.tin', 'next.tin'], target: 'linux-amd64', runArguments: ['$(echo unsafe)', 'a b']}, '/workspace', '/workspace/main.tin', 'build');
  assert.equal(config.compiler, '/workspace/tool chain/tinc');
  assert.deepEqual(compileArguments(config, '/output/a b'), ['-edition', '1', '-target', 'linux-amd64', '-o', '/output/a b', '/workspace/a b.tin', '/workspace/next.tin']);
  assert.deepEqual(compileArguments({...config, edition: '0'}, '/output').slice(0, 2), ['-target', 'linux-amd64']);
  assert.deepEqual(config.runArguments, ['$(echo unsafe)', 'a b']);
  assert.equal(configuration({target: 'linux-amd64'}, '/workspace', '/workspace/main.tin', 'run').target, 'native');
  assert.equal(configuration({target: 'linux-arm64'}, '/workspace', '/workspace/main.tin', 'test').target, 'native');
});

test('test discovery rejects malformed signatures and ignores comments, literals and lowercase helpers', () => {
  const source = 'package demo\n// fn TestComment(t mut crucible.T) {\nlet example = `\nfn TestString(t mut crucible.T) {\n`\nfn Testhelper() {}\nfn TestReal(t mut crucible.T) {\n}\n';
  const result = testRunner([{file: '/demo/test.tin', source}], '1');
  assert.equal(result.count, 1);
  assert.equal(result.entry, 'demo.TinEditorTestMain');
  assert.match(result.source, /crucible.Run\("TestReal", TestReal\)/);
  assert.throws(() => testRunner([{file: '/bad.tin', source: 'package main\nfn TestBad() {\n}'}], '1'), /bad.tin:2:1/);
  assert.throws(() => testRunner([{file: '/bad.tin', source: 'package main\nfunc TestOld(t mut crucible.T) {\n}'}], '1'), /Expected fn/);
  assert.match(testRunner([{file: '/old.tin', source: 'package main\nfunc TestOld(t mut crucible.T) {\n}'}], '0').source, /func TinEditorTestMain/);
});

test('problem matcher handles file paths with spaces and colons', () => {
  const regex = new RegExp(manifest.contributes.problemMatchers[0].pattern.regexp);
  const result = regex.exec('/workspace/a:b c.tin:12:9: error: mismatch');
  assert.deepEqual(result.slice(1), ['/workspace/a:b c.tin', '12', '9', 'mismatch']);
});

test('failed compile never runs an executable, and successful temporary runs clean up', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'tin-extension test-'));
  try {
    const fake = path.join(dir, 'fake compiler');
    const record = path.join(dir, 'output-path');
    await fs.writeFile(fake, `#!/usr/bin/env node\nconst fs = require('node:fs');\nconst out = process.argv[process.argv.indexOf('-o') + 1];\nfs.writeFileSync(${JSON.stringify(record)}, out);\nfs.writeFileSync(out, '#!/bin/sh\\nprintf "PROGRAM-RAN\\\\n"\\n', {mode: 0o755});\nprocess.exit(process.argv.includes('bad.tin') ? 7 : 0);\n`, {mode: 0o755});
    const base = {action: 'run', cwd: dir, compiler: fake, root: '', edition: '1', target: 'native', runArguments: []};
    // Run the real CLI bridge to capture its output and exit status.
    const result = spawnSync(process.execPath, [path.resolve(__dirname, '../src/runner.js'), JSON.stringify({...base, files: ['bad.tin']})], {encoding: 'utf8'});
    assert.equal(result.status, 7);
    assert.doesNotMatch(result.stdout, /PROGRAM-RAN/);
    const output = await fs.readFile(record, 'utf8');
    await assert.rejects(fs.access(path.dirname(output)));
    const success = spawnSync(process.execPath, [path.resolve(__dirname, '../src/runner.js'), JSON.stringify({...base, files: ['ok.tin']})], {encoding: 'utf8'});
    assert.equal(success.status, 0, success.stderr);
    assert.match(success.stdout, /PROGRAM-RAN/);
    await assert.rejects(fs.access(path.dirname(await fs.readFile(record, 'utf8'))));
    await assert.rejects(execute({...base, compiler: path.join(dir, 'missing'), files: ['ok.tin']}), /ENOENT/);
  } finally {await fs.rm(dir, {recursive: true, force: true});}
});

const compiler = process.env.TIN_VSCODE_COMPILER;
test('real edition-1 compile, run, diagnostics, crucible success and failure', {skip: !compiler}, async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'tin native test-'));
  const run = config => spawnSync(process.execPath, [path.resolve(__dirname, '../src/runner.js'), JSON.stringify(config)], {encoding: 'utf8', timeout: 30000});
  try {
    const example = path.join(dir, 'hello.tin');
    await fs.copyFile(path.join(__dirname, 'fixtures/hello.tin'), example);
    const config = configuration({compilerPath: compiler, toolchainRoot: process.env.TIN_ROOT}, dir, example, 'run');
    const result = run(config);
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout, 'Hello Yasser, trailblazer!\nRange total: 6\n');
    const checked = run({...config, action: 'check'});
    assert.equal(checked.status, 0, checked.stderr);
    const build = run({...config, action: 'build', outputDirectory: path.join(dir, 'build')});
    assert.equal(build.status, 0, build.stderr);
    assert.equal(spawnSync(path.join(dir, 'build/hello-native'), [], {encoding: 'utf8'}).stdout, result.stdout);
    await fs.writeFile(example, 'package main\nfn main() {\n    let x i64 = "bad"\n}\n');
    const invalid = run(config);
    assert.notEqual(invalid.status, 0);
    assert.match(invalid.stderr, /hello.tin:\d+:\d+:/);
    await fs.rm(example);
    const tests = path.join(dir, 'sum_test.tin');
    const testSource = 'package sample\nimport "crucible"\nfn TestSum(t mut crucible.T) {\n    crucible.Equal(mut t, "sum", 2 + 3, 5)\n}\n';
    await fs.writeFile(tests, testSource);
    const testConfig = {...config, action: 'test', directory: dir};
    const passed = run(testConfig);
    assert.equal(passed.status, 0, passed.stderr);
    assert.match(passed.stdout, /PASS/);
    await fs.writeFile(tests, testSource.replace('2 + 3, 5', '2 + 3, 6'));
    const failed = run(testConfig);
    assert.equal(failed.status, 1, failed.stderr);
    assert.match(failed.stdout, /FAIL/);
  } finally {await fs.rm(dir, {recursive: true, force: true});}
});
