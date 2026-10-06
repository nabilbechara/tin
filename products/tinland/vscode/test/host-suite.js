'use strict';
const assert = require('node:assert/strict');
const vscode = require('vscode');
async function run() {
  const extension = vscode.extensions.getExtension('yasserreslan.tin-language');
  assert.ok(extension);
  await extension.activate();
  const commands = await vscode.commands.getCommands(true);
  for (const action of ['build', 'run', 'check', 'test']) assert.ok(commands.includes(`tin.${action}`));
  const folder = vscode.workspace.workspaceFolders[0];
  const document = await vscode.workspace.openTextDocument(vscode.Uri.joinPath(folder.uri, 'hello.tin'));
  assert.equal(document.languageId, 'tin');
  await vscode.window.showTextDocument(document);
  let tasks = [];
  const tasksDeadline = Date.now() + 5000;
  while (tasks.length !== 4 && Date.now() < tasksDeadline) {
    await vscode.window.showTextDocument(document);
    tasks = await vscode.tasks.fetchTasks({type: 'tin'});
    if (tasks.length !== 4) await new Promise(resolve => setTimeout(resolve, 100));
  }
  assert.equal(tasks.length, 4);
  if (process.env.TIN_VSCODE_COMPILER) {
    async function execute(action, expected) {
      const selected = tasks.find(t => t.definition.action === action);
      await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {listener.dispose(); reject(new Error(`Tin ${action} task timed out`));}, 30000);
        const listener = vscode.tasks.onDidEndTaskProcess(event => {
          if (event.execution.task.definition.type !== 'tin' || event.execution.task.definition.action !== action) return;
          clearTimeout(timeout); listener.dispose();
          try {assert.equal(event.exitCode, expected); resolve();} catch (err) {reject(err);}
        });
        vscode.tasks.executeTask(selected).catch(err => {clearTimeout(timeout); listener.dispose(); reject(err);});
      });
    }
    await execute('check', 0);
    await execute('build', 0);
    await execute('run', 0);
    const testUri = vscode.Uri.joinPath(folder.uri, 'hello_test.tin');
    await vscode.workspace.fs.writeFile(testUri, Buffer.from('package main\nimport "crucible"\nfn TestHello(t mut crucible.T) {\n    crucible.Equal(mut t, "sum", 2 + 3, 5)\n}\n'));
    await execute('test', 0);
    await vscode.workspace.fs.writeFile(document.uri, Buffer.from('package main\nfn main() {\n    let x i64 = "bad"\n}\n'));
    await execute('check', 1);
    // Wait for the task problem matcher to publish its compiler diagnostic.
    const deadline = Date.now() + 5000;
    while (!vscode.languages.getDiagnostics(document.uri).length && Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    const diagnostics = vscode.languages.getDiagnostics(document.uri);
    assert.ok(diagnostics.length, 'Compiler errors must reach the Problems panel');
    assert.equal(diagnostics[0].range.start.line, 2);
    async function waitForLiveErrors(present, predicate = () => true) {
      const deadline = Date.now() + 10000;
      while (Date.now() < deadline) {
        const items = vscode.languages.getDiagnostics(document.uri).filter(d => d.source === 'Tin');
        if (Boolean(items.length) === present && (!present || items.some(predicate))) return items;
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      throw new Error(`Expected automatic diagnostics present=${present}`);
    }
    async function replace(text) {
      const edit = new vscode.WorkspaceEdit();
      edit.replace(document.uri, new vscode.Range(0, 0, document.lineCount, 0), text);
      assert.ok(await vscode.workspace.applyEdit(edit));
    }
    // Red squiggles must update for unsaved edits without invoking a task.
    await replace('package main\nfn main() {\n    let x = @\n}\n');
    const syntaxErrors = await waitForLiveErrors(true, d => /expected|unexpected|attribute/.test(d.message));
    assert.equal(syntaxErrors[0].severity, vscode.DiagnosticSeverity.Error);
    assert.equal(syntaxErrors[0].range.start.line, 2);
    await replace('package main\nfn main() {\n    let x = 1\n}\n');
    await waitForLiveErrors(false);
    // Type errors must appear in unsaved buffers, without a manual compile.
    await replace('package main\nfn main() {\n    let x i64 = "bad"\n}\n');
    const typeErrors = await waitForLiveErrors(true, d => /str|i64/.test(d.message));
    assert.ok(document.isDirty);
    assert.match(typeErrors[0].message, /str|i64/);
    await replace('package main\nfn main() {\n    let x i64 = 1\n}\n');
    assert.ok(await document.save());
    await waitForLiveErrors(false);
    assert.equal(vscode.languages.getDiagnostics(document.uri).length, 0, 'Correcting code must clear all open-file squiggles, including manual task errors');

    const declarations = 'package main\nimport "say"\n// Greets a user.\nfn greet(name str, count i64) str {\n    return name\n}\ntype User struct {\n    Name str\n}\nfn main() {\n    let user = User{Name: "x"}\n    let count i64 = 1\n';
    async function completionAt(suffix) {
      await replace(declarations + suffix);
      const position = document.positionAt(document.getText().length);
      return await vscode.commands.executeCommand('vscode.executeCompletionItemProvider', document.uri, position);
    }
    let suggestions = await completionAt('    say.');
    assert.ok(suggestions.items.some(item => item.label === 'Line'), 'say. must suggest compiler builtin Line');
    assert.ok(suggestions.items.some(item => item.label === 'Fmt'));
    for (const name of ['Line', 'Text', 'Out', 'Fmt', 'Str', 'Fault', 'To', 'LineTo']) {
      assert.ok(suggestions.items.some(item => item.label === name && item.detail && item.documentation), `say.${name} needs a documented completion`);
    }
    async function definitionAt(text, offset) {
      await replace(text);
      return vscode.commands.executeCommand('vscode.executeDefinitionProvider', document.uri, document.positionAt(offset));
    }
    let navigationText = 'package main\nimport "say"\nfn main() { say.Line("hello") }\n';
    let targets = await definitionAt(navigationText, navigationText.indexOf('"say"') + 2);
    assert.ok(targets[0].uri.fsPath.endsWith('/toolchain/std/say/say.tin'), 'Command-click on an import opens its package');
    const links = await vscode.commands.executeCommand('vscode.executeLinkProvider', document.uri);
    assert.ok(links.some(link => link.target?.fsPath.endsWith('/toolchain/std/say/say.tin')), 'Import paths must also be clickable document links');
    targets = await definitionAt(navigationText, navigationText.indexOf('say.Line') + 1);
    assert.ok(targets[0].uri.fsPath.endsWith('/toolchain/std/say/say.tin'), 'Command-click on a package qualifier opens its package');
    const localUri = vscode.Uri.joinPath(folder.uri, 'geom.tin');
    await vscode.workspace.fs.writeFile(localUri, Buffer.from('package geom\nfn Area() i64 { return 1 }\n'));
    navigationText = 'package main\nimport "./geom"\nfn main() { geom.Area() }\n';
    targets = await definitionAt(navigationText, navigationText.indexOf('./geom') + 3);
    assert.equal(targets[0].uri.fsPath, localUri.fsPath, 'Relative single-file imports resolve like the compiler');
    targets = await definitionAt(navigationText, navigationText.indexOf('Area') + 1);
    assert.equal(targets[0].uri.fsPath, localUri.fsPath);
    assert.equal(targets[0].range.start.line, 1);
    const vendorUri = vscode.Uri.joinPath(folder.uri, 'vendor', 'say', 'say.tin');
    await vscode.workspace.fs.createDirectory(vscode.Uri.joinPath(folder.uri, 'vendor', 'say'));
    await vscode.workspace.fs.writeFile(vendorUri, Buffer.from('package say\nfn Custom() {}\n'));
    navigationText = 'package main\nimport "say"\nfn main() { say.Custom() }\n';
    targets = await definitionAt(navigationText, navigationText.indexOf('"say"') + 2);
    assert.equal(targets[0].uri.fsPath, vendorUri.fsPath, 'Vendor package takes precedence over the standard library');
    suggestions = await completionAt('    say.');
    assert.ok(suggestions.items.some(item => item.label === 'Custom'));
    assert.ok(!suggestions.items.some(item => item.label === 'Line'), 'Vendored say uses its own declarations');
    await vscode.workspace.fs.delete(vscode.Uri.joinPath(folder.uri, 'vendor'), {recursive: true});
    suggestions = await completionAt('    user.');
    assert.ok(suggestions.items.some(item => item.label === 'Name'), 'typed receiver must suggest its fields');
    assert.ok(!suggestions.items.some(item => item.label === 'Line'), 'receiver suggestions must be contextual');
    suggestions = await completionAt('    cou');
    assert.ok(suggestions.items.some(item => item.label === 'count'), 'local variables must be suggested');
    await replace(declarations + '    greet("x", ');
    const signature = await vscode.commands.executeCommand('vscode.executeSignatureHelpProvider', document.uri, document.positionAt(document.getText().length));
    assert.ok(signature.signatures[0].label.includes('greet(name str, count i64)'));
    assert.equal(signature.activeParameter, 1);
    await replace(declarations + '    let message = greet("x", 1)\n}\n');
    const callOffset = document.getText().lastIndexOf('greet');
    const hovers = await vscode.commands.executeCommand('vscode.executeHoverProvider', document.uri, document.positionAt(callOffset + 1));
    assert.ok(hovers.some(h => h.contents.some(c => (c.value || '').replace(/&nbsp;/g, ' ').includes('Greets a user'))));
    const definitions = await vscode.commands.executeCommand('vscode.executeDefinitionProvider', document.uri, document.positionAt(callOffset + 1));
    assert.equal(definitions[0].range.start.line, 3);
    const symbols = await vscode.commands.executeCommand('vscode.executeDocumentSymbolProvider', document.uri);
    assert.ok(symbols.some(s => s.name === 'User' && s.children.some(c => c.name === 'Name')));
    const lenses = await vscode.commands.executeCommand('vscode.executeCodeLensProvider', document.uri);
    assert.ok(lenses.some(l => l.command?.command === 'tin.run'));
    await replace('package main\nfn main() {\n    within 200 ms {\n        1\n    }\n}\n');
    const unitErrors = await waitForLiveErrors(true, d => /expected/.test(d.message));
    const fixes = await vscode.commands.executeCommand('vscode.executeCodeActionProvider', document.uri, unitErrors[0].range);
    assert.ok(fixes.some(f => f.title.includes('Join unit literal: 200ms')));
    await replace('package main\nfn main() {\nlet x = 1\n}\n');
    const formatted = await vscode.commands.executeCommand('vscode.executeFormatDocumentProvider', document.uri, {insertSpaces: true, tabSize: 4});
    assert.ok(formatted.length, 'Format Document must produce edits');
    const formatting = new vscode.WorkspaceEdit();
    formatting.set(document.uri, formatted);
    assert.ok(await vscode.workspace.applyEdit(formatting));
    assert.equal(document.lineAt(2).text, '    let x = 1');
  }
  console.log('Tin VS Code extension host checks passed.');
}
module.exports = {run};
