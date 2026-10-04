'use strict';
const vscode = require('vscode');
const path = require('node:path');
const {configuration} = require('./core');

function activate(context) {
  require('./diagnostics').registerDiagnostics(context);
  require('./intelligence').registerIntelligence(context);
  require('./editing').registerEditing(context);
  function createTask(action, uri, folder, definition) {
    if (!vscode.workspace.isTrusted) throw new Error('Trust this workspace before executing Tin code.');
    if (!uri || uri.scheme !== 'file') throw new Error('Open a saved .tin file first.');
    const cwd = folder?.uri.fsPath || path.dirname(uri.fsPath);
    const settings = vscode.workspace.getConfiguration('tin', uri);
    const config = configuration(settings, cwd, uri.fsPath, action);
    const execution = new vscode.ProcessExecution(process.execPath,
      [context.asAbsolutePath('src/runner.js'), JSON.stringify(config)],
      {cwd, env: {ELECTRON_RUN_AS_NODE: '1'}});
    const task = new vscode.Task(definition || {type: 'tin', action, file: path.relative(cwd, uri.fsPath)},
      folder || vscode.TaskScope.Global, `${action}: ${path.basename(uri.fsPath)}`, 'Tin', execution, ['$tin']);
    if (action === 'build') task.group = vscode.TaskGroup.Build;
    if (action === 'test') task.group = vscode.TaskGroup.Test;
    task.presentationOptions = {reveal: vscode.TaskRevealKind.Always, panel: vscode.TaskPanelKind.Shared, clear: true};
    return task;
  }
  for (const action of ['build', 'run', 'check', 'test']) {
    context.subscriptions.push(vscode.commands.registerCommand(`tin.${action}`, async () => {
      try {
        const doc = vscode.window.activeTextEditor?.document;
        if (!doc || doc.languageId !== 'tin' || doc.isUntitled) throw new Error('Open and save a .tin file first.');
        if (!vscode.workspace.isTrusted) throw new Error('Trust this workspace before executing Tin code.');
        // Compilation may include other open files from the package.
        if (!(await vscode.workspace.saveAll(false))) throw new Error('Save the source files before compiling.');
        const folder = vscode.workspace.getWorkspaceFolder(doc.uri);
        await vscode.tasks.executeTask(createTask(action, doc.uri, folder));
      } catch (err) {vscode.window.showErrorMessage(`Tin: ${err.message}`);}
    }));
  }
  context.subscriptions.push(vscode.tasks.registerTaskProvider('tin', {
    provideTasks() {
      const doc = vscode.window.activeTextEditor?.document;
      if (!vscode.workspace.isTrusted || !doc || doc.languageId !== 'tin' || doc.isUntitled) return [];
      const folder = vscode.workspace.getWorkspaceFolder(doc.uri);
      if (!folder) return [];
      return ['build', 'run', 'check', 'test'].map(action => createTask(action, doc.uri, folder));
    },
    resolveTask(task) {
      if (!vscode.workspace.isTrusted) return undefined;
      const folder = typeof task.scope === 'object' ? task.scope : undefined;
      if (!folder) return undefined;
      const uri = task.definition.file
        ? vscode.Uri.file(path.resolve(folder.uri.fsPath, task.definition.file))
        : vscode.window.activeTextEditor?.document.uri;
      if (!uri) return undefined;
      try {return createTask(task.definition.action, uri, folder, task.definition);}
      catch (err) {vscode.window.showErrorMessage(`Tin: ${err.message}`); return undefined;}
    }
  }));
}
module.exports = {activate};
