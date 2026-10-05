'use strict';
const {tokenize, analyze, visibleSymbols} = require('./analysis');

function indentSource(text, options) {
  const eol = text.includes('\r\n') ? '\r\n' : '\n';
  const unit = options.insertSpaces ? ' '.repeat(options.tabSize) : '\t';
  const tokens = tokenize(text);
  let depth = 0, offset = 0;
  return text.split(/\r?\n/).map(line => {
    const start = offset, end = start + line.length;
    offset = end + eol.length;
    const literal = tokens.find(t => t.kind === 'string' && t.start < start && t.end > start);
    if (literal) return line;
    const onLine = tokens.filter(t => t.start >= start && t.start < end && !['comment', 'string'].includes(t.kind));
    let leading = 0;
    while (['}', ')', ']'].includes(onLine[leading]?.value)) leading++;
    const indented = line.trim() ? unit.repeat(Math.max(0, depth - leading)) + line.trimStart().trimEnd() : '';
    for (const token of onLine) {
      if (['{', '(', '['].includes(token.value)) depth++;
      if (['}', ')', ']'].includes(token.value)) depth = Math.max(0, depth - 1);
    }
    return indented;
  }).join(eol);
}
function distance(a, b) {
  const rows = Array.from({length: a.length + 1}, (_, i) => [i]);
  for (let j = 0; j <= b.length; j++) rows[0][j] = j;
  for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++) rows[i][j] = Math.min(rows[i - 1][j] + 1, rows[i][j - 1] + 1, rows[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
  return rows[a.length][b.length];
}
function registerEditing(context) {
  const vscode = require('vscode');
  const selector = {language: 'tin'};
  context.subscriptions.push(vscode.languages.registerDocumentFormattingEditProvider(selector, {
    provideDocumentFormattingEdits(document, options) {
      const formatted = indentSource(document.getText(), options);
      if (formatted === document.getText()) return [];
      return [vscode.TextEdit.replace(new vscode.Range(0, 0, document.lineCount, 0), formatted)];
    }
  }));
  context.subscriptions.push(vscode.languages.registerCodeActionsProvider(selector, {
    provideCodeActions(document, range, context) {
      const actions = [];
      const model = analyze(document.getText());
      for (const diagnostic of context.diagnostics) {
        if (!['Tin', 'tinc'].includes(diagnostic.source)) continue;
        const row = diagnostic.range.start.line;
        if (row >= document.lineCount) continue;
        const text = document.lineAt(row).text;
        function action(title, editRange, value) {
          const item = new vscode.CodeAction(title, vscode.CodeActionKind.QuickFix);
          item.diagnostics = [diagnostic]; item.edit = new vscode.WorkspaceEdit();
          item.edit.replace(document.uri, editRange, value); actions.push(item);
        }
        const unit = /\b(\d+(?:\.\d+)?)\s+(ns|us|ms|s|m|h|kb|mb|gb|b)\b/.exec(text);
        if (unit && /expected|unexpected/.test(diagnostic.message)) {
          action(`Join unit literal: ${unit[1]}${unit[2]}`, new vscode.Range(row, unit.index, row, unit.index + unit[0].length), unit[1] + unit[2]);
        }
        if (diagnostic.message.includes('return cannot leave a boundary block')) {
          const found = /\breturn\s+/.exec(text);
          if (found) action('Use the last expression as the block value', new vscode.Range(row, found.index, row, found.index + found[0].length), '');
        }
        if (/undefined|unknown name/.test(diagnostic.message)) {
          const wordRange = document.getWordRangeAtPosition(diagnostic.range.start);
          if (!wordRange) continue;
          const word = document.getText(wordRange);
          if (word.length < 3) continue;
          const candidates = visibleSymbols(model, document.offsetAt(wordRange.start)).filter(s => s.name !== word && distance(word, s.name) <= 2).sort((a, b) => distance(word, a.name) - distance(word, b.name)).slice(0, 3);
          for (const candidate of candidates) action(`Change to '${candidate.name}'`, wordRange, candidate.name);
        }
      }
      return actions;
    }
  }, {providedCodeActionKinds: [vscode.CodeActionKind.QuickFix]}));
  context.subscriptions.push(vscode.languages.registerCodeLensProvider(selector, {
    provideCodeLenses(document) {
      const model = analyze(document.getText());
      const lenses = [];
      for (const sym of model.symbols) {
        if (sym.kind !== 'function' || sym.scope.start !== 0) continue;
        const range = new vscode.Range(document.positionAt(sym.start), document.positionAt(sym.end));
        if (sym.name === 'main') {
          lenses.push(new vscode.CodeLens(range, {title: '▶ Run', command: 'tin.run'}));
          lenses.push(new vscode.CodeLens(range, {title: 'Build', command: 'tin.build'}));
        } else if (/^Test[^a-z]/.test(sym.name)) lenses.push(new vscode.CodeLens(range, {title: 'Test package', command: 'tin.test'}));
      }
      return lenses;
    }
  }));
}
module.exports = {registerEditing, indentSource};
