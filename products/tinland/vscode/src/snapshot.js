'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');

// Mirror directories with links, replacing only open buffers with private copies.
async function snapshotProject(directory, root, files, buffers) {
  const project = path.join(directory, 'workspace');
  await fs.mkdir(project);
  const materialized = new Set();
  const inside = file => !path.relative(root, file).startsWith(`..${path.sep}`) && path.relative(root, file) !== '..' && !path.isAbsolute(path.relative(root, file));
  function map(file) {return inside(file) ? path.join(project, path.relative(root, file)) : file;}
  async function materialize(original) {
    if (materialized.has(original)) return;
    if (original !== root) await materialize(path.dirname(original));
    const target = map(original);
    if (original !== root) await fs.unlink(target).catch(err => {if (err.code !== 'ENOENT') throw err;});
    await fs.mkdir(target, {recursive: true});
    const entries = await fs.readdir(original, {withFileTypes: true});
    for (const entry of entries) {
      await fs.symlink(path.join(original, entry.name), path.join(target, entry.name), entry.isDirectory() ? 'dir' : 'file');
    }
    materialized.add(original);
  }
  for (const buffer of buffers) {
    if (!inside(buffer.file)) continue;
    await materialize(path.dirname(buffer.file));
    const target = map(buffer.file);
    await fs.unlink(target).catch(err => {if (err.code !== 'ENOENT') throw err;});
    await fs.writeFile(target, buffer.text);
  }
  if (!materialized.has(root)) await materialize(root);
  return {files: files.map(map), project, original(file) {
    const relative = path.relative(project, file);
    return relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative) ? file : path.join(root, relative);
  }};
}
module.exports = {snapshotProject};
