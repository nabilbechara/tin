'use strict';
const {test, before} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {Registry, parseRawGrammar, INITIAL} = require('vscode-textmate');
const oniguruma = require('vscode-oniguruma');
let grammar;
before(async () => {
  const wasm = fs.readFileSync(require.resolve('vscode-oniguruma/release/onig.wasm'));
  await oniguruma.loadWASM(wasm.buffer.slice(wasm.byteOffset, wasm.byteOffset + wasm.byteLength));
  const registry = new Registry({onigLib: Promise.resolve({createOnigScanner: s => new oniguruma.OnigScanner(s), createOnigString: s => new oniguruma.OnigString(s)}),
    loadGrammar: async () => parseRawGrammar(fs.readFileSync(path.resolve(__dirname, '../syntaxes/tin.tmLanguage.json'), 'utf8'), 'tin.json')});
  grammar = await registry.loadGrammar('source.tin');
});
function scopes(line, text) {
  const at = line.indexOf(text);
  const result = grammar.tokenizeLine(line, INITIAL);
  return result.tokens.find(t => t.startIndex <= at && t.endIndex > at).scopes;
}
test('policy expressions, types, duration, ranges, and optional defaults get distinct scopes', () => {
  assert.ok(scopes('let x = try with retry(3) {', 'with').includes('keyword.control.tin'));
  assert.ok(scopes('fn greeting(id i64) !str {', 'fn').includes('storage.type.function.tin'));
  assert.ok(scopes('fn greeting(id i64) !str {', 'greeting').includes('entity.name.function.tin'));
  assert.ok(scopes('let x = within 200ms {', '200ms').includes('constant.numeric.tin'));
  assert.ok(scopes('for i in 0..4 {', '..').includes('keyword.operator.tin'));
  assert.ok(scopes('let x = maybe ?? "name"', '??').includes('keyword.operator.tin'));
  assert.ok(scopes('token secret str', 'str').includes('support.type.tin'));
});
test('interpolation highlights expressions, while raw strings and comments stay literal', () => {
  assert.ok(scopes('say.Line("Hello {badge(120)}")', 'badge').includes('entity.name.function.tin'));
  assert.ok(scopes('say.Line(`Hello {badge(120)}`)', 'badge').includes('string.quoted.raw.tin'));
  assert.ok(!scopes('say.Line(`Hello {badge(120)}`)', 'badge').includes('meta.interpolation.tin'));
  assert.ok(scopes('// with retry(3)', 'with').includes('comment.line.double-slash.tin'));
  assert.ok(scopes('let x = "{{literal}}"', 'literal').includes('string.quoted.double.tin'));
  assert.ok(!scopes('let x = "{{literal}}"', 'literal').includes('meta.interpolation.tin'));
});
