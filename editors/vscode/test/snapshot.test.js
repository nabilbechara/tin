'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {snapshotProject} = require('../src/snapshot');
const {spawnSync} = require('node:child_process');

test('snapshot overlays local imports and sibling buffers without changing original files', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'tin-overlay-'));
  try {
    const source = path.join(root, 'source');
    const temp = path.join(root, 'private');
    await fs.mkdir(path.join(source, 'geom'), {recursive: true}); await fs.mkdir(temp);
    const main = path.join(source, 'main.tin');
    const helper = path.join(source, 'geom/helper.tin');
    await fs.writeFile(main, 'saved'); await fs.writeFile(helper, 'saved helper');
    const snapshot = await snapshotProject(temp, source, [main], [{file: main, text: 'edited'}, {file: helper, text: 'edited helper'}]);
    assert.equal(await fs.readFile(snapshot.files[0], 'utf8'), 'edited');
    assert.equal(await fs.readFile(path.join(snapshot.project, 'geom/helper.tin'), 'utf8'), 'edited helper');
    assert.equal(await fs.readFile(main, 'utf8'), 'saved');
    assert.equal(await fs.readFile(helper, 'utf8'), 'saved helper');
    assert.equal(snapshot.original(snapshot.files[0]), main);
    assert.equal(snapshot.original('/elsewhere/lib.tin'), '/elsewhere/lib.tin');
  } finally {await fs.rm(root, {recursive: true, force: true});}
});

test('compiler diagnoses an unsaved type error across a local import', {skip: !process.env.TIN_VSCODE_COMPILER}, async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'tin-import-overlay-'));
  try {
    const source = path.join(root, 'source'); const temp = path.join(root, 'private');
    await fs.mkdir(path.join(source, 'geom'), {recursive: true}); await fs.mkdir(temp);
    const main = path.join(source, 'main.tin'); const helper = path.join(source, 'geom/helper.tin');
    await fs.writeFile(main, 'package main\nimport "./geom"\nfn main() {\n    let x = geom.Value()\n}\n');
    await fs.writeFile(helper, 'package geom\nfn Value() i64 {\n    return 3\n}\n');
    const snapshot = await snapshotProject(temp, source, [main], [{file: helper, text: 'package geom\nfn Value() i64 {\n    return "wrong"\n}\n'}]);
    const result = spawnSync(process.env.TIN_VSCODE_COMPILER, ['-edition', '1', '-o', path.join(temp, 'out'), ...snapshot.files], {encoding: 'utf8', env: process.env});
    assert.equal(result.status, 1);
    assert.match(result.stderr, /cannot use str as i64/);
    assert.match(result.stderr, /geom\/helper.tin:3:/);
    assert.equal(await fs.readFile(helper, 'utf8'), 'package geom\nfn Value() i64 {\n    return 3\n}\n');
  } finally {await fs.rm(root, {recursive: true, force: true});}
});
