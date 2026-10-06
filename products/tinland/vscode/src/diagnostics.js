'use strict';
const vscode = require('vscode');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {configuration, compileArguments} = require('./core');
const {snapshotProject} = require('./snapshot');

function registerDiagnostics(context) {
  const collection = vscode.languages.createDiagnosticCollection('tin-live');
  const output = vscode.window.createOutputChannel('Tin Checks');
  const pending = new Map();
  const results = new Map();
  let disposed = false;
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 15);
  status.command = 'tin.showChecks';
  function showStatus() {if (vscode.window.activeTextEditor?.document.languageId === 'tin') status.show(); else status.hide();}
  status.text = '$(check) Tin';
  showStatus();
  context.subscriptions.push(status, vscode.commands.registerCommand('tin.showChecks', () => output.show()), vscode.window.onDidChangeActiveTextEditor(showStatus));
  function publish() {
    const combined = new Map();
    for (const groups of results.values()) {
      for (const [file, items] of groups) {
        const existing = combined.get(file) || [];
        for (const item of items) {
          if (!existing.some(d => d.message === item.message && d.range.isEqual(item.range))) existing.push(item);
        }
        combined.set(file, existing);
      }
    }
    collection.clear();
    for (const [file, items] of combined) collection.set(vscode.Uri.file(file), items);
  }
  function cancel(key) {
    const state = pending.get(key);
    if (state) {clearTimeout(state.timer); state.child?.kill('SIGKILL'); pending.delete(key);}
  }
  function schedule(doc, full, forced = false) {
    if (disposed || doc.languageId !== 'tin' || doc.uri.scheme !== 'file' || doc.isUntitled) return;
    const key = doc.uri.toString();
    cancel(key);
    const settings = vscode.workspace.getConfiguration('tin', doc.uri);
    if (!vscode.workspace.isTrusted || (!forced && (full ? !settings.get('checkOnSave', true) : !settings.get('liveSyntaxChecks', true)))) return;
    const state = {version: doc.version};
    status.text = '$(sync~spin) Tin: checking';
    state.timer = setTimeout(() => check(doc, full, state), full ? 0 : settings.get('checkDelay', 250));
    pending.set(key, state);
  }
  async function check(doc, full, state) {
    const key = doc.uri.toString();
    let temp;
    try {
      const folder = vscode.workspace.getWorkspaceFolder(doc.uri);
      const cwd = folder?.uri.fsPath || path.dirname(doc.uri.fsPath);
      const config = configuration(vscode.workspace.getConfiguration('tin', doc.uri), cwd, doc.uri.fsPath, 'check');
      temp = await fs.mkdtemp(path.join(os.tmpdir(), 'tin-diagnostics-'));
      let mapped = {original: file => file};
      let args;
      const buffers = vscode.workspace.textDocuments.filter(d => d.uri.scheme === 'file' && d.languageId === 'tin' && d.isDirty)
        .map(d => ({file: d.uri.fsPath, text: d.getText()}));
      if (buffers.length) {
        mapped = await snapshotProject(temp, cwd, config.files, buffers);
        args = compileArguments(config, path.join(temp, 'check-output'), mapped.files);
      } else {
        args = compileArguments(config, path.join(temp, 'check-output'));
      }
      if (pending.get(key) !== state || disposed) return;
      const result = await new Promise((resolve, reject) => {
        const child = spawn(config.compiler, args, {cwd, env: {...process.env, ...(config.root ? {TIN_ROOT: config.root} : {})}, stdio: ['ignore', 'ignore', 'pipe']});
        state.child = child;
        let text = '';
        let timedOut = false;
        const timeout = setTimeout(() => {timedOut = true; child.kill('SIGKILL');}, 15000);
        child.stderr.setEncoding('utf8');
        child.stderr.on('data', chunk => {if (text.length < 1024 * 1024) text += chunk.toString();});
        child.once('error', err => {clearTimeout(timeout); reject(err);});
        child.once('close', code => {clearTimeout(timeout); if (timedOut) reject(new Error('Compiler check timed out after 15 seconds')); else resolve({stderr: text, code});});
      });
      if (disposed || pending.get(key) !== state || doc.version !== state.version) return;
      const groups = new Map();
      for (const line of result.stderr.split(/\r?\n/)) {
        const match = /^(.+):(\d+):(\d+): (?:error: )?(.*)$/.exec(line);
        if (!match) {if (line) output.appendLine(line); continue;}
        const file = mapped.original(path.resolve(cwd, match[1]));
        const row = Math.max(0, Number(match[2]) - 1);
        let column = Math.max(0, Number(match[3]) - 1);
        let end = column + 1;
        const open = vscode.workspace.textDocuments.find(d => d.uri.fsPath === file);
        if (open && row < open.lineCount) {
          const text = open.lineAt(row).text;
          column = Math.min(column, text.length);
          end = Math.min(text.length, column + (text.slice(column).match(/^\w+/)?.[0].length || 1));
        }
        const diagnostic = new vscode.Diagnostic(new vscode.Range(row, column, row, end), match[4], vscode.DiagnosticSeverity.Error);
        diagnostic.source = 'Tin';
        const items = groups.get(file) || [];
        items.push(diagnostic);
        groups.set(file, items);
      }
      results.set(key, groups);
      publish();
      const count = [...groups.values()].reduce((n, items) => n + items.length, 0);
      if (result.code !== 0 && !count) {
        status.text = '$(warning) Tin: check unavailable';
        status.tooltip = result.stderr.trim() || 'Compiler exited without a diagnostic; see Tin Checks';
        return;
      }
      status.text = count ? `$(error) Tin: ${count} error${count === 1 ? '' : 's'}` : '$(check) Tin';
      status.tooltip = count ? 'Compiler diagnostics — see Problems' : 'Compiler check passed';
    } catch (err) {
      if (!disposed && pending.get(key) === state) {
        output.appendLine(`Check failed: ${err.message}. Configure tin.compilerPath and tin.toolchainRoot.`);
        status.text = '$(warning) Tin: check unavailable';
        status.tooltip = `${err.message} — click to view Tin Checks`;
      }
    } finally {
      if (pending.get(key) === state) pending.delete(key);
      if (temp) await fs.rm(temp, {recursive: true, force: true});
    }
  }
  context.subscriptions.push(collection, output,
    vscode.tasks.onDidEndTaskProcess(event => {
      const task = event.execution.task;
      if (task.definition.type !== 'tin') return;
      const folder = typeof task.scope === 'object' ? task.scope : undefined;
      const file = folder && task.definition.file ? path.resolve(folder.uri.fsPath, task.definition.file) : undefined;
      const doc = file ? vscode.workspace.textDocuments.find(d => d.uri.fsPath === file) : vscode.window.activeTextEditor?.document;
      if (doc) schedule(doc, true, true);
    }),
    vscode.workspace.onDidOpenTextDocument(doc => schedule(doc, !doc.isDirty)),
    vscode.workspace.onDidChangeTextDocument(event => {
      if (!event.contentChanges.length) return;
      schedule(event.document, false);
      // Refresh checks that previously reported errors in this dependency.
      for (const [owner, groups] of results) {
        if (owner === event.document.uri.toString() || !groups.has(event.document.uri.fsPath)) continue;
        const dependent = vscode.workspace.textDocuments.find(d => d.uri.toString() === owner);
        if (dependent) schedule(dependent, false);
      }
    }),
    vscode.workspace.onDidSaveTextDocument(doc => schedule(doc, true)),
    vscode.workspace.onDidCloseTextDocument(doc => {const key = doc.uri.toString(); cancel(key); results.delete(key); publish();}),
    vscode.workspace.onDidGrantWorkspaceTrust(() => vscode.workspace.textDocuments.forEach(doc => schedule(doc, !doc.isDirty))),
    vscode.workspace.onDidChangeConfiguration(event => {
      if (event.affectsConfiguration('tin')) {
        for (const key of pending.keys()) cancel(key);
        results.clear(); publish();
        vscode.workspace.textDocuments.forEach(doc => schedule(doc, !doc.isDirty));
      }
    }),
    {dispose() {disposed = true; for (const key of pending.keys()) cancel(key);}}
  );
  vscode.workspace.textDocuments.forEach(doc => schedule(doc, !doc.isDirty));
}
module.exports = {registerDiagnostics};
