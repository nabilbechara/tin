'use strict';
const {runTests, downloadAndUnzipVSCode} = require('@vscode/test-electron');
const path = require('node:path');
const fs = require('node:fs/promises');
const os = require('node:os');
(async () => {
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), 'tin-vscode-host-'));
  try {
    await fs.copyFile(path.resolve(__dirname, 'fixtures/hello.tin'), path.join(workspace, 'hello.tin'));
    await fs.mkdir(path.join(workspace, '.vscode'));
    await fs.writeFile(path.join(workspace, '.vscode/settings.json'), JSON.stringify({
      'tin.compilerPath': process.env.TIN_VSCODE_COMPILER || '', 'tin.toolchainRoot': process.env.TIN_ROOT || '', 'tin.edition': '1'
    }));
    let executable = process.env.TIN_VSCODE_EXECUTABLE || await downloadAndUnzipVSCode();
    // Recent macOS distributions renamed Electron to Code.
    try {await fs.access(executable);} catch (err) {
      if (path.basename(executable) !== 'Electron') throw err;
      executable = path.join(path.dirname(executable), 'Code');
      await fs.access(executable);
    }
    await runTests({vscodeExecutablePath: executable, extensionDevelopmentPath: path.resolve(__dirname, '..'), extensionTestsPath: path.resolve(__dirname, 'host-suite.js'),
      launchArgs: [workspace, '--disable-workspace-trust', '--skip-welcome', '--skip-release-notes'], extensionTestsEnv: {TIN_VSCODE_COMPILER: process.env.TIN_VSCODE_COMPILER || ''}});
  } finally {await fs.rm(workspace, {recursive: true, force: true});}
})().catch(err => {console.error(err); process.exitCode = 1;});
