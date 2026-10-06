'use strict';
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {compileArguments, testRunner} = require('./core');

function processRun(command, args, config) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {cwd: config.cwd, env: {...process.env, ...(config.root ? {TIN_ROOT: config.root} : {})}, stdio: 'inherit'});
    let canceled = false;
    let forceStop;
    const stop = () => {
      canceled = true;
      child.kill('SIGTERM');
      forceStop = setTimeout(() => child.kill('SIGKILL'), 5000);
      forceStop.unref();
    };
    process.once('SIGTERM', stop);
    process.once('SIGINT', stop);
    child.once('error', err => {cleanup(); reject(err);});
    child.once('exit', (code, signal) => {cleanup(); resolve(canceled ? 130 : code ?? (signal ? 130 : 1));});
    function cleanup() {clearTimeout(forceStop); process.removeListener('SIGTERM', stop); process.removeListener('SIGINT', stop);}
  });
}
async function execute(config) {
  let temp;
  try {
    let files = config.files;
    let entry;
    if (config.action !== 'build') temp = await fs.mkdtemp(path.join(os.tmpdir(), 'tin-vscode-'));
    if (config.action === 'test') {
      const names = (await fs.readdir(config.directory)).filter(n => n.endsWith('.tin')).sort();
      const testFiles = names.filter(n => n.endsWith('_test.tin'));
      if (!testFiles.length) {console.log('Tin: no *_test.tin files in this package.'); return 0;}
      const sources = await Promise.all(testFiles.map(async n => {
        const file = path.join(config.directory, n);
        return {file, source: await fs.readFile(file, 'utf8')};
      }));
      const runner = testRunner(sources, config.edition);
      if (!runner.count) throw new Error('No TestXxx functions found. Expected a test name whose first character after Test is not lowercase.');
      const runnerFile = path.join(temp, 'runner.tin');
      await fs.writeFile(runnerFile, runner.source);
      files = [...names.map(n => path.join(config.directory, n)), runnerFile];
      entry = runner.entry;
    }
    if (config.action === 'build') await fs.mkdir(config.outputDirectory, {recursive: true});
    const output = config.action === 'build'
      ? path.join(config.outputDirectory, `${path.basename(files[0], '.tin')}-${config.target}`)
      : path.join(temp, 'program');
    const code = await processRun(config.compiler, compileArguments(config, output, files, entry), config);
    if (code !== 0) return code;
    if (config.action === 'run' || config.action === 'test') return await processRun(output, config.action === 'run' ? config.runArguments : [], config);
    console.log(config.action === 'build' ? `Tin: built ${output}` : 'Tin: compile check passed.');
    return 0;
  } finally {
    if (temp) await fs.rm(temp, {recursive: true, force: true});
  }
}
if (require.main === module) {
  Promise.resolve().then(() => execute(JSON.parse(process.argv[2]))).then(code => {process.exitCode = code;}).catch(err => {
    console.error(`Tin: ${err.message}`);
    if (err.code === 'ENOENT') console.error('Configure tin.compilerPath to the tinc executable and tin.toolchainRoot to the Tin installation root.');
    process.exitCode = 1;
  });
}
module.exports = {execute};
