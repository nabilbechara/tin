'use strict';
const fs = require('node:fs');
const path = require('node:path');

function resolvePath(value, cwd) {
  return path.isAbsolute(value) ? value : path.resolve(cwd, value);
}
function configuration(settings, cwd, file, action) {
  if (!['build', 'run', 'check', 'test'].includes(action)) throw new Error('Unknown Tin action.');
  const root = settings.toolchainRoot ? resolvePath(settings.toolchainRoot, cwd)
    : fs.existsSync(path.join(cwd, 'bin', 'tinc')) && (fs.existsSync(path.join(cwd, 'toolchain', 'runtime')) || fs.existsSync(path.join(cwd, 'lib'))) ? cwd : '';
  const compiler = settings.compilerPath
    ? (settings.compilerPath.includes('/') || settings.compilerPath.includes('\\') ? resolvePath(settings.compilerPath, cwd) : settings.compilerPath)
    : root ? path.join(root, 'bin', 'tinc') : 'tinc';
  const files = settings.entryFiles?.length ? settings.entryFiles.map(f => resolvePath(f, cwd)) : [file];
  if (files.some(f => !f || !f.endsWith('.tin'))) throw new Error('Select a saved .tin file or configure tin.entryFiles.');
  const edition = String(settings.edition ?? '1');
  if (!['0', '1'].includes(edition)) throw new Error('tin.edition must be 0 or 1.');
  const target = settings.target ?? 'native';
  if (!['native', 'linux-arm64', 'linux-amd64', 'darwin-arm64'].includes(target)) throw new Error('Unsupported Tin target.');
  return {action, cwd, compiler, root, edition, target: ['run', 'test'].includes(action) ? 'native' : target,
    files, directory: path.dirname(file || files[0]), outputDirectory: resolvePath(settings.outputDirectory || '.tin-build', cwd),
    runArguments: settings.runArguments || []};
}
function compileArguments(config, output, files = config.files, entry) {
  const args = config.edition === '1' ? ['-edition', '1'] : [];
  if (config.target !== 'native') args.push('-target', config.target);
  if (entry) args.push('-entry', entry);
  return [...args, '-o', output, ...files];
}

// Mask comments and literals without changing positions, so commented-out tests are ignored.
function maskSource(source) {
  return source.replace(/\/\/[^\n]*|`[^`]*`|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'/g,
    text => text.replace(/[^\n]/g, ' '));
}
function testRunner(sources, edition) {
  const keyword = edition === '1' ? 'fn' : 'func';
  let pkg;
  const tests = [];
  for (const {file, source} of sources) {
    const masked = maskSource(source);
    const name = masked.match(/^\s*package\s+([A-Za-z_]\w*)/m)?.[1];
    if (!name) throw new Error(`${file}:1:1: error: Test file has no package clause.`);
    if (pkg && name !== pkg) throw new Error(`${file}:1:1: error: Test files must share one package.`);
    pkg = name;
    const declarations = /^\s*(fn|func)\s+(Test\w*)\s*([^\n]*)/gm;
    let m;
    while ((m = declarations.exec(masked))) {
      if (/^Test[a-z]/.test(m[2])) continue;
      const line = masked.slice(0, m.index + m[0].indexOf(m[1])).split('\n').length;
      if (m[1] !== keyword || !/^\(\s*[A-Za-z_]\w*\s+mut\s+crucible\.T\s*,?\s*\)\s*\{\s*$/.test(m[3])) {
        throw new Error(`${file}:${line}:1: error: Expected ${keyword} ${m[2]}(t mut crucible.T) {`);
      }
      tests.push(m[2]);
    }
  }
  if (new Set(tests).size !== tests.length) throw new Error('Duplicate test function names.');
  const functionName = 'TinEditorTestMain';
  return {count: tests.length, entry: pkg === 'main' ? functionName : `${pkg}.${functionName}`,
    source: `package ${pkg}\nimport "crucible"\n${keyword} ${functionName}() {\n${tests.map(t => `    crucible.Run("${t}", ${t})`).join('\n')}\n    crucible.Finish()\n}\n`};
}
module.exports = {configuration, compileArguments, maskSource, testRunner};
