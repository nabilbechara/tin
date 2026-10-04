'use strict';
const vscode = require('vscode');
const fs = require('node:fs/promises');
const path = require('node:path');
const {configuration} = require('./core');
const {analyze, visibleSymbols, callContext} = require('./analysis');

const keywordHelp = {
  fn: 'Declares a function. Every result path ends in return. Capitalized names are exported.',
  let: 'Binds a name that cannot be reassigned. The referenced object can still be mutable.',
  mut: 'Declares a mutable binding or parameter. Mutable parameters require mut at the call site.',
  with: 'Applies a policy to a block. The last expression supplies its value. Use try or catch to handle faults. Policies expose Run(body); policy.Retry, Bind, Trace and Cached are provided by the library.',
  within: 'Applies a deadline, for example within 200ms { ... }. The block yields its last expression; return cannot leave the block.',
  try: 'Propagates a fault from a fallible expression. The enclosing function must return !T or !.',
  catch: 'Handles a fault. The last expression supplies the fallback value; the fault must be checked.',
  match: 'Pattern matching with => arms. Enum matches must be exhaustive. Arms supply the match expression value.',
  keep: 'Copies request data into long-lived memory.',
  secret: 'Marks sensitive values. Sinks and declassification are checked by the compiler when implemented.'
};
const keywords = 'fn let mut const type struct shape enum dyn if else for in match return break continue defer try catch fail keep within limit guard scope arena parallel select detach with use on once secret max shared package import nil true false'.split(' ');
const builtins = {len: 'len(value) i64', cap: 'cap(value) i64', append: 'append(slice, value) []T', make: 'make(type, length, capacity)', copy: 'copy(destination, source) i64', delete: 'delete(map, key)', panic: 'panic(message str)', keep: 'keep(value) T'};
const sayFunctions = {Line: ['values...', 'Prints values separated by spaces, followed by a newline.'], Text: ['values...', 'Prints values without added spaces or a newline.'], Out: ['format str, values...', 'Prints formatted values.'], Fmt: ['format str, values...', 'Formats values and returns str.'], Str: ['value', 'Returns the string representation of a value.'], Fault: ['format str, values...', 'Creates a formatted fault value.'], To: ['fd i64, values...', 'Prints values to a file descriptor.'], LineTo: ['fd i64, values...', 'Prints a line to a file descriptor.']};
const primitiveTypes = 'i8 i16 i32 i64 u8 u16 u32 u64 f32 f64 bool str rune Duration Size fault query'.split(' ');

function registerIntelligence(context) {
  const selector = {language: 'tin'};
  const cache = new Map();
  async function model(file) {
    const open = vscode.workspace.textDocuments.find(d => d.uri.scheme === 'file' && d.uri.fsPath === file);
    if (open) return {...analyze(open.getText()), file};
    const stat = await fs.stat(file);
    const previous = cache.get(file);
    if (previous?.mtime === stat.mtimeMs && previous.size === stat.size) return previous.model;
    const indexed = {...analyze(await fs.readFile(file, 'utf8')), file};
    cache.set(file, {mtime: stat.mtimeMs, size: stat.size, model: indexed});
    return indexed;
  }
  async function packageModels(directory) {
    try {
      try {await fs.access(directory + '.tin'); directory += '.tin';} catch {}
      const stat = await fs.stat(directory);
      const files = stat.isDirectory() ? (await fs.readdir(directory)).filter(n => !n.startsWith('.') && n.endsWith('.tin') && !n.endsWith('_test.tin')).sort().map(n => path.join(directory, n)) : [directory];
      const read = await Promise.allSettled(files.map(model));
      return read.filter(r => r.status === 'fulfilled').map(r => r.value);
    } catch {return [];}
  }
  async function environment(document) {
    const folder = vscode.workspace.getWorkspaceFolder(document.uri) || vscode.workspace.workspaceFolders?.[0];
    const cwd = folder?.uri.fsPath || (document.uri.scheme === 'file' ? path.dirname(document.uri.fsPath) : process.cwd());
    const file = document.uri.scheme === 'file' ? document.uri.fsPath : path.join(cwd, 'untitled.tin');
    const current = {...analyze(document.getText()), file};
    let config;
    try {config = configuration(vscode.workspace.getConfiguration('tin', document.uri), cwd, file, 'check');} catch {config = {root: ''};}
    let root = config.root;
    if (!root && path.isAbsolute(config.compiler || '')) {
      const candidate = path.dirname(path.dirname(config.compiler));
      try {await fs.access(path.join(candidate, 'lib')); root = candidate;} catch {}
    }
    if (!root && document.uri.scheme === 'file') {
      let directory = path.dirname(file);
      while (true) {
        try {
          await fs.access(path.join(directory, 'lib'));
          await fs.access(path.join(directory, 'bin', 'tinc'));
          root = directory;
          break;
        } catch {}
        const parent = path.dirname(directory);
        if (parent === directory) break;
        directory = parent;
      }
    }
    const siblings = (await packageModels(path.dirname(file))).filter(m => m.file !== file);
    const imported = new Map();
    await Promise.all(current.imports.map(async imp => {
      const candidates = imp.path.startsWith('.') ? [path.resolve(path.dirname(file), imp.path)]
        : [path.join(path.dirname(config.files?.[0] || file), 'vendor', imp.path), ...(root ? [path.join(root, 'lib', imp.path)] : []), path.resolve(path.dirname(config.files?.[0] || file), imp.path)];
      let models = [];
      for (const candidate of candidates) {
        models = await packageModels(candidate);
        if (models.length) break;
      }
      imported.set(imp.name, models);
    }));
    return {current, siblings, imported, root};
  }
  function entries(models) {return models.flatMap(m => m.symbols.map(s => ({...s, file: m.file})));}
  function globals(env) {return entries(env.siblings).filter(s => s.scope.start === 0 && !['method', 'parameter'].includes(s.kind));}
  function local(env, offset) {
    return visibleSymbols(env.current, offset).filter(s => s.kind !== 'method').map(s => ({...s, file: env.current.file}));
  }
  function members(env, receiver, offset) {
    if (receiver === 'say' && env.root && env.imported.get('say')?.some(m => m.file === path.join(env.root, 'lib', 'say', 'say.tin'))) return Object.entries(sayFunctions).map(([name, [parameters, description]]) => ({name, kind: 'function', params: parameters.split(', '), signature: `say.${name}(${parameters})`, documentation: `${description} Compiler builtin; accepts values of different static types.`}));
    if (env.imported.has(receiver)) return entries(env.imported.get(receiver)).filter(s => /^[A-Z]/.test(s.name) && s.scope.start === 0 && !['parameter', 'method'].includes(s.kind));
    const symbols = [...local(env, offset), ...globals(env)];
    const binding = symbols.find(s => s.name === receiver);
    let type = (binding?.type || (env.current.types.has(receiver) ? receiver : '')).replace(/^[!?]/, '').replace(/^mut\s+/, '').replace(/\[.*$/, '');
    let models = [env.current, ...env.siblings];
    let foreign = false;
    if (type.includes('.')) {
      const [pkg, name] = type.split('.');
      type = name; models = env.imported.get(pkg) || []; foreign = true;
    }
    const foundType = models.map(m => ({model: m, type: m.types.get(type)})).find(v => v.type);
    const fields = foundType ? foundType.type.fields.map(s => ({...s, file: foundType.model.file})) : [];
    return [...fields, ...entries(models).filter(s => s.kind === 'method' && s.owner === type)].filter(s => !foreign || /^[A-Z]/.test(s.name));
  }
  function lookup(env, name, receiver, offset) {
    const declaration = env.current.symbols.find(s => s.name === name && s.start <= offset && s.end >= offset);
    if (!receiver && declaration) return {...declaration, file: env.current.file};
    return receiver ? members(env, receiver, offset).find(s => s.name === name) : [...local(env, offset), ...globals(env)].find(s => s.name === name);
  }
  function contextAt(document, position) {
    const range = document.getWordRangeAtPosition(position, /[A-Za-z_]\w*/);
    if (!range) return undefined;
    const before = document.getText(new vscode.Range(new vscode.Position(0, 0), range.start));
    return {name: document.getText(range), receiver: before.match(/([A-Za-z_]\w*)\.\s*$/)?.[1], range};
  }
  function inLiteral(document, position) {
    const offset = document.offsetAt(position);
    const tokens = analyze(document.getText()).tokens;
    const token = tokens.find(t => t.start <= offset && t.end > offset);
    return token && ['comment', 'string'].includes(token.kind) || tokens.some(t => t.kind === 'comment' && t.end === offset);
  }
  function documentation(sym) {
    const doc = new vscode.MarkdownString();
    doc.appendCodeblock(sym.signature || `${sym.name}${sym.type ? ` ${sym.type}` : ''}`, 'tin');
    if (sym.documentation) doc.appendText(`\n${sym.documentation}`);
    return doc;
  }
  function packageSource(env, name) {
    const models = env.imported.get(name) || [];
    return models.find(m => path.basename(m.file) === `${name}.tin`) || models[0];
  }
  context.subscriptions.push(vscode.languages.registerDocumentLinkProvider(selector, {
    async provideDocumentLinks(document) {
      const env = await environment(document);
      return env.current.imports.flatMap(imp => {
        const source = packageSource(env, imp.name);
        if (!source) return [];
        const range = new vscode.Range(document.positionAt(imp.start + 1), document.positionAt(imp.end - 1));
        const link = new vscode.DocumentLink(range, vscode.Uri.file(source.file));
        link.tooltip = `Open Tin package ${imp.path}`;
        return [link];
      });
    }
  }));
  function completion(sym) {
    const kinds = {function: vscode.CompletionItemKind.Function, method: vscode.CompletionItemKind.Method, type: vscode.CompletionItemKind.Struct, variable: vscode.CompletionItemKind.Variable, parameter: vscode.CompletionItemKind.Variable, field: vscode.CompletionItemKind.Field, constant: vscode.CompletionItemKind.Constant, enum: vscode.CompletionItemKind.EnumMember};
    const item = new vscode.CompletionItem(sym.name, kinds[sym.kind]);
    item.detail = sym.signature || `${sym.name}${sym.type ? ` ${sym.type}` : ''}`;
    item.documentation = documentation(sym);
    item.sortText = `0_${sym.name}`;
    return item;
  }
  context.subscriptions.push(vscode.languages.registerCompletionItemProvider(selector, {
    async provideCompletionItems(document, position, token) {
      const line = document.lineAt(position.line).text.slice(0, position.character);
      const env = await environment(document);
      if (token.isCancellationRequested) return [];
      if (/^\s*import\s+"[^"\n]*$/.test(line)) {
        if (!env.root) return [];
        const prefix = line.slice(line.indexOf('"') + 1);
        if (prefix.startsWith('.')) return [];
        const directories = await fs.readdir(path.join(env.root, 'lib'), {withFileTypes: true}).catch(() => []);
        return directories.filter(d => d.isDirectory()).map(d => new vscode.CompletionItem(d.name, vscode.CompletionItemKind.Module));
      }
      if (inLiteral(document, position)) return [];
      const receiver = line.match(/([A-Za-z_]\w*)\.\w*$/)?.[1];
      if (receiver) return members(env, receiver, document.offsetAt(position)).map(completion);
      const all = [...local(env, document.offsetAt(position)), ...globals(env)];
      const seen = new Set();
      const items = all.filter(s => {if (seen.has(s.name)) return false; seen.add(s.name); return true;}).map(completion);
      for (const imp of env.current.imports) items.push(new vscode.CompletionItem(imp.name, vscode.CompletionItemKind.Module));
      for (const name of primitiveTypes) items.push(new vscode.CompletionItem(name, vscode.CompletionItemKind.TypeParameter));
      for (const name of keywords) {
        if (seen.has(name)) continue;
        const item = new vscode.CompletionItem(name, vscode.CompletionItemKind.Keyword);
        item.documentation = keywordHelp[name]; item.sortText = `2_${name}`; items.push(item);
      }
      for (const [name, signature] of Object.entries(builtins)) {
        if (seen.has(name)) continue;
        const item = new vscode.CompletionItem(name, vscode.CompletionItemKind.Function); item.detail = signature; items.push(item);
      }
      return items;
    }
  }, '.', '"'));
  context.subscriptions.push(vscode.languages.registerHoverProvider(selector, {
    async provideHover(document, position) {
      if (inLiteral(document, position)) return undefined;
      const at = contextAt(document, position);
      if (!at) return undefined;
      const env = await environment(document);
      const sym = lookup(env, at.name, at.receiver, document.offsetAt(position));
      if (sym) return new vscode.Hover(documentation(sym), at.range);
      if (keywordHelp[at.name]) return new vscode.Hover(keywordHelp[at.name], at.range);
      if (builtins[at.name]) return new vscode.Hover(new vscode.MarkdownString().appendCodeblock(builtins[at.name], 'tin'), at.range);
    }
  }));
  context.subscriptions.push(vscode.languages.registerDefinitionProvider(selector, {
    async provideDefinition(document, position) {
      const env = await environment(document);
      const offset = document.offsetAt(position);
      const imported = env.current.imports.find(i => i.start <= offset && i.end >= offset);
      const at = contextAt(document, position);
      const packageName = imported?.name || (!inLiteral(document, position) && !at?.receiver && at?.name);
      // Imports are string literals, but unlike ordinary strings they are navigation targets.
      if (packageName && env.imported.has(packageName) && (imported || !lookup(env, packageName, undefined, offset))) {
        const preferred = packageSource(env, packageName);
        if (!preferred) return undefined;
        const target = await vscode.workspace.openTextDocument(vscode.Uri.file(preferred.file));
        const clause = preferred.text.match(/\bpackage\s+([A-Za-z_]\w*)/);
        const start = clause ? clause.index + clause[0].lastIndexOf(clause[1]) : 0;
        return new vscode.Location(target.uri, new vscode.Range(target.positionAt(start), target.positionAt(start + (clause?.[1].length || 0))));
      }
      if (inLiteral(document, position)) return undefined;
      if (!at) return undefined;
      const sym = lookup(env, at.name, at.receiver, document.offsetAt(position));
      if (!sym?.file) return undefined;
      const target = await vscode.workspace.openTextDocument(vscode.Uri.file(sym.file));
      return new vscode.Location(target.uri, new vscode.Range(target.positionAt(sym.start), target.positionAt(sym.end)));
    }
  }));
  context.subscriptions.push(vscode.languages.registerSignatureHelpProvider(selector, {
    async provideSignatureHelp(document, position) {
      if (inLiteral(document, position)) return undefined;
      const call = callContext(document.getText(), document.offsetAt(position));
      if (!call) return undefined;
      const env = await environment(document);
      const sym = lookup(env, call.name, call.receiver, document.offsetAt(position));
      if (!sym?.params) return undefined;
      const help = new vscode.SignatureHelp();
      const signature = new vscode.SignatureInformation(sym.signature, sym.documentation);
      signature.parameters = sym.params.map(p => new vscode.ParameterInformation(p));
      help.signatures = [signature]; help.activeSignature = 0;
      help.activeParameter = Math.min(call.argument, Math.max(0, sym.params.length - 1));
      return help;
    }
  }, '(', ','));
  context.subscriptions.push(vscode.languages.registerDocumentSymbolProvider(selector, {
    provideDocumentSymbols(document) {
      const model = analyze(document.getText());
      return model.symbols.filter(s => s.scope.start === 0 && s.kind !== 'parameter').map(s => {
        const kind = s.kind === 'type' ? vscode.SymbolKind.Struct : ['function', 'method'].includes(s.kind) ? vscode.SymbolKind.Function : vscode.SymbolKind.Variable;
        const range = new vscode.Range(document.positionAt(s.start), document.positionAt(s.blockEnd || s.end));
        const result = new vscode.DocumentSymbol(s.name, s.type || '', kind, range, new vscode.Range(document.positionAt(s.start), document.positionAt(s.end)));
        if (s.fields) result.children = s.fields.map(f => new vscode.DocumentSymbol(f.name, f.type, vscode.SymbolKind.Field, new vscode.Range(document.positionAt(f.start), document.positionAt(f.end)), new vscode.Range(document.positionAt(f.start), document.positionAt(f.end))));
        return result;
      });
    }
  }));
  context.subscriptions.push({dispose() {cache.clear();}});
}
module.exports = {registerIntelligence};
