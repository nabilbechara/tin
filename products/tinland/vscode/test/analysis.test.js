'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {analyze, visibleSymbols, splitParameters, callContext} = require('../src/analysis');
const {indentSource} = require('../src/editing');

test('declaration index preserves signatures, documentation and nested parameter types', () => {
  const source = 'package main\n// Loads a user.\nfn load(id i64, opts map[str]i64) !User {\n    let user = User{name: "x"}\n    return user\n}\ntype User struct {\n    name str\n    age i64\n}\n';
  const model = analyze(source);
  const fn = model.symbols.find(s => s.name === 'load');
  assert.equal(fn.documentation, 'Loads a user.');
  assert.equal(fn.type, '!User');
  assert.deepEqual(fn.params, ['id i64', 'opts map[str]i64']);
  assert.deepEqual(model.types.get('User').fields.map(s => [s.name, s.type]), [['name', 'str'], ['age', 'i64']]);
  assert.equal(model.symbols.find(s => s.name === 'user').type, 'User');
  assert.deepEqual(splitParameters('a, b i64, body fn(i64, str) !str'), ['a i64', 'b i64', 'body fn(i64, str) !str']);
});

test('visible declarations respect nested scopes, shadowing and declaration order', () => {
  const text = 'package main\nfn first(value i64) {\n    let outer = 1\n    if true {\n        let outer = "text"\n        print(outer)\n    }\n    print(outer)\n    let later = 3\n}\nfn second(other str) {\n    print(other)\n}\n';
  const model = analyze(text);
  const nested = visibleSymbols(model, text.indexOf('print(outer)'));
  assert.equal(nested.find(s => s.name === 'outer').type, 'str');
  assert.equal(nested.find(s => s.name === 'value').type, 'i64');
  assert.ok(!nested.some(s => s.name === 'later' || s.name === 'other'));
  const outside = visibleSymbols(model, text.lastIndexOf('print(outer)'));
  assert.equal(outside.find(s => s.name === 'outer').type, 'i64');
  assert.ok(!visibleSymbols(model, text.indexOf('print(other)')).some(s => s.name === 'value' || s.name === 'outer'));
});

test('call argument index handles nesting, strings and generic calls', () => {
  assert.deepEqual(callContext('load(1, other("a,b"), ', 24), {name: 'load', receiver: undefined, argument: 2});
  const text = 'db.Query[User]("select", ';
  assert.deepEqual(callContext(text, text.length), {name: 'Query', receiver: 'db', argument: 1});
});

test('initializer calls and loop and catch bindings respect their scopes', () => {
  const text = 'package main\nfn name() !str { return "x" }\nfn main() {\n let name = name() catch err {\n  use(err)\n  "guest"\n }\n use(name)\n for i in 0..4 {\n  use(i)\n }\n use(name)\n}\n';
  const model = analyze(text);
  assert.equal(visibleSymbols(model, text.indexOf('name() catch')).find(s => s.name === 'name').kind, 'function');
  assert.equal(visibleSymbols(model, text.indexOf('use(err)')).find(s => s.name === 'err').type, 'fault');
  assert.equal(visibleSymbols(model, text.indexOf('use(i)')).find(s => s.name === 'i').type, 'i64');
  const after = visibleSymbols(model, text.lastIndexOf('use(name)'));
  assert.equal(after.find(s => s.name === 'name').type, 'str');
  assert.ok(!after.some(s => s.name === 'err' || s.name === 'i'));
});

test('indent formatting preserves raw literal contents and operators', () => {
  const text = 'fn main() {\nlet message = `a\n  literal spacing\n`\nif true {\nsay.Line(message)\n}\n}\n';
  assert.equal(indentSource(text, {insertSpaces: true, tabSize: 4}), 'fn main() {\n    let message = `a\n  literal spacing\n`\n    if true {\n        say.Line(message)\n    }\n}\n');
});
