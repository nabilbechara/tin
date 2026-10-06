'use strict';

function tokenize(text) {
  const tokens = [];
  const pattern = /\/\/[^\n]*|`[^`]*`|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[A-Za-z_]\w*|\d[\w.]*(?:[eE][+-]?\d+)?|=>|\?\?|\.\.|:=|[^\s]/g;
  let m;
  while ((m = pattern.exec(text))) {
    const value = m[0];
    const kind = value.startsWith('//') ? 'comment' : /^["'`]/.test(value) ? 'string' : /^\d/.test(value) ? 'number' : /^\w/.test(value) ? 'word' : 'punctuation';
    tokens.push({value, kind, start: m.index, end: pattern.lastIndex});
  }
  return tokens;
}
function splitParameters(text) {
  const parts = [];
  let depth = 0, start = 0;
  for (let i = 0; i < text.length; i++) {
    if ('([{'.includes(text[i])) depth++;
    if (')]}'.includes(text[i])) depth--;
    if (text[i] === ',' && depth === 0) {parts.push(text.slice(start, i).trim()); start = i + 1;}
  }
  if (text.slice(start).trim()) parts.push(text.slice(start).trim());
  for (let i = parts.length - 2; i >= 0; i--) {
    if (/^[A-Za-z_]\w*$/.test(parts[i])) parts[i] += ` ${parts[i + 1].replace(/^[A-Za-z_]\w*\s+/, '')}`;
  }
  return parts;
}
function analyze(text) {
  const allTokens = tokenize(text);
  const tokens = allTokens.filter(t => t.kind !== 'comment');
  const pairs = new Map();
  const stack = [];
  const braces = [];
  for (let i = 0; i < tokens.length; i++) {
    const v = tokens[i].value;
    if ('([{'.includes(v) && v.length === 1) stack.push(i);
    if (')]}'.includes(v) && v.length === 1 && stack.length) {
      const begin = stack[stack.length - 1];
      if ('([{'.indexOf(tokens[begin].value) === ')]}'.indexOf(v)) {
        stack.pop(); pairs.set(begin, i);
        if (v === '}') braces.push({start: tokens[begin].start, end: tokens[i].end});
      }
    }
  }
  const symbols = [];
  const imports = [];
  const types = new Map();
  const doc = start => {
    const lines = text.slice(0, start).split('\n');
    if (lines[lines.length - 1].trim()) return '';
    lines.pop();
    const comments = [];
    while (lines.length && /^\s*\/\//.test(lines[lines.length - 1])) comments.unshift(lines.pop().replace(/^\s*\/\/\s?/, ''));
    return comments.join('\n');
  };
  const scope = offset => braces.filter(b => b.start < offset && b.end >= offset).sort((a, b) => (a.end - a.start) - (b.end - b.start))[0] || {start: 0, end: text.length};
  const symbol = (name, kind, extras = {}) => ({name: name.value, start: name.start, end: name.end, kind, scope: scope(name.start), ...extras});
  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i];
    const next = tokens[i + 1];
    if (token.value === 'import' && next?.kind === 'string') {
      const imported = next.value.slice(1, -1);
      imports.push({name: imported.split('/').pop(), path: imported, start: next.start, end: next.end});
    }
    if (token.value === 'catch' && next?.kind === 'word' && tokens[i + 2]?.value === '{') {
      const body = i + 2, end = pairs.get(body);
      symbols.push(symbol(next, 'parameter', {type: 'fault', scope: {start: tokens[body].start, end: end === undefined ? text.length : tokens[end].end}}));
    }
    if (token.value === 'for' && next?.kind === 'word') {
      let j = i + 1;
      const names = [tokens[j++]];
      if (tokens[j]?.value === ',' && tokens[j + 1]?.kind === 'word') {j++; names.push(tokens[j++]);}
      if (tokens[j]?.value === 'in') {
        const sequence = tokens[j + 1];
        let body = j + 2;
        while (body < tokens.length && tokens[body].value !== '{' && !text.slice(tokens[body - 1].end, tokens[body].start).includes('\n')) body++;
        if (tokens[body]?.value === '{') {
          const end = pairs.get(body);
          const binding = symbols.find(s => s.name === sequence?.value);
          for (let n = 0; n < names.length; n++) {
            const type = sequence?.kind === 'number' || names.length > 1 && n === 0 ? 'i64' : binding?.type?.startsWith('[]') ? binding.type.slice(2) : '';
            symbols.push(symbol(names[n], 'parameter', {type, scope: {start: tokens[body].start, end: end === undefined ? text.length : tokens[end].end}}));
          }
        }
      }
    }
    if (token.value === 'type' && next?.kind === 'word') {
      const sym = symbol(next, 'type', {signature: '', documentation: doc(token.start), fields: []});
      let j = i + 2;
      if (tokens[j]?.value === '[' && pairs.has(j)) j = pairs.get(j) + 1;
      const typeKind = tokens[j]?.value;
      if (['struct', 'enum'].includes(typeKind) && tokens[j + 1]?.value === '{') {
        const begin = j + 1, end = pairs.get(begin) ?? tokens.length - 1;
        sym.typeKind = typeKind; sym.blockEnd = tokens[end].end;
        let k = begin + 1;
        while (k < end) {
          if (tokens[k].value === '@') {
            k += 2;
            if (tokens[k]?.value === '(' && pairs.has(k)) k = pairs.get(k) + 1;
            continue;
          }
          if (tokens[k].kind !== 'word') {k++; continue;}
          const field = tokens[k];
          let finish = k + 1;
          if (typeKind === 'enum') {
            if (tokens[finish]?.value === '(' && pairs.has(finish)) finish = pairs.get(finish) + 1;
          } else {
            while (finish < end && !text.slice(tokens[finish - 1].end, tokens[finish].start).includes('\n')) finish++;
          }
          const type = typeKind === 'enum' ? next.value : text.slice(field.end, tokens[finish - 1]?.end || field.end).trim();
          sym.fields.push(symbol(field, typeKind === 'enum' ? 'enum' : 'field', {type, owner: sym.name, documentation: doc(field.start)}));
          k = Math.max(finish, k + 1);
        }
      }
      sym.signature = `type ${sym.name} ${typeKind || ''}`;
      types.set(sym.name, sym); symbols.push(sym);
    }
    if (['fn', 'func'].includes(token.value)) {
      let j = i + 1, receiver;
      if (tokens[j]?.value === '(' && pairs.has(j)) {
        const end = pairs.get(j);
        receiver = text.slice(tokens[j].end, tokens[end].start).trim(); j = end + 1;
      }
      if (tokens[j]?.kind !== 'word') continue;
      const name = tokens[j++];
      if (tokens[j]?.value === '[' && pairs.has(j)) j = pairs.get(j) + 1;
      if (tokens[j]?.value !== '(' || !pairs.has(j)) continue;
      const paramEnd = pairs.get(j);
      const params = splitParameters(text.slice(tokens[j].end, tokens[paramEnd].start));
      let body = paramEnd + 1;
      while (body < tokens.length && tokens[body].value !== '{' && !text.slice(tokens[body - 1].end, tokens[body].start).includes('\n')) body++;
      const returns = text.slice(tokens[paramEnd].end, tokens[body]?.start ?? tokens[paramEnd].end).trim();
      const end = pairs.get(body);
      const bodyScope = {start: tokens[body]?.start ?? name.end, end: end === undefined ? text.length : tokens[end].end};
      const fn = symbol(name, receiver ? 'method' : 'function', {params, type: returns, receiver, owner: receiver?.replace(/^\w+\s+(?:mut\s+)?/, '').replace(/\[.*$/, ''), documentation: doc(token.start), signature: text.slice(token.start, tokens[body]?.start ?? tokens[paramEnd].end).trim(), blockEnd: bodyScope.end});
      symbols.push(fn);
      for (const param of [...params, ...(receiver ? [receiver] : [])]) {
        const m = /^(\w+)\s+(.+)$/.exec(param);
        if (!m) continue;
        const found = tokens.slice(i + 1, paramEnd + 1).find(t => t.value === m[1]);
        if (found) symbols.push(symbol(found, 'parameter', {type: m[2].replace(/^mut\s+/, ''), scope: bodyScope}));
      }
    }
    if (['let', 'mut', 'var', 'const', 'use'].includes(token.value) && next?.kind === 'word') {
      if (symbols.some(s => s.start === next.start)) continue;
      let j = i + 2;
      while (j < tokens.length && !['=', ':=', '{', '}'].includes(tokens[j].value) && !text.slice(tokens[j - 1].end, tokens[j].start).includes('\n')) j++;
      const declared = text.slice(next.end, tokens[j]?.start ?? next.end).trim();
      let type = declared;
      const value = tokens[j]?.value === '=' ? tokens[j + 1] : undefined;
      if (!type && value) {
        type = value.kind === 'string' ? 'str' : value.kind === 'number' ? (/ms$|[smh]$/.test(value.value) ? 'Duration' : /(?:kb|mb|gb|b)$/.test(value.value) ? 'Size' : value.value.includes('.') ? 'f64' : 'i64') : ['true', 'false'].includes(value.value) ? 'bool' : tokens[j + 2]?.value === '{' ? value.value : '';
      }
      const availableFrom = text.indexOf('\n', next.end);
      symbols.push(symbol(next, token.value === 'const' ? 'constant' : 'variable', {type, availableFrom: availableFrom < 0 ? text.length : availableFrom, initializer: value?.value, initializerIsCall: tokens[j + 2]?.value === '(', signature: text.slice(token.start, tokens[j]?.start ?? next.end).trim()}));
    }
  }
  return {text, tokens: allTokens, symbols, imports, types};
}
function visibleSymbols(model, offset) {
  const selected = new Map();
  for (const sym of model.symbols) {
    const global = sym.scope.start === 0;
    if (!global && !(sym.scope.start <= offset && sym.scope.end >= offset && (sym.kind === 'parameter' || (sym.availableFrom ?? sym.start) <= offset))) continue;
    const old = selected.get(sym.name);
    if (!old || sym.scope.start > old.scope.start || (sym.scope.start === old.scope.start && sym.start > old.start)) selected.set(sym.name, sym);
  }
  for (const sym of selected.values()) {
    if (!sym.type && sym.initializer) {
      const from = sym.initializerIsCall ? model.symbols.find(s => s.name === sym.initializer && s.kind === 'function') : selected.get(sym.initializer);
      sym.type = from?.type?.replace(/^!/, '') || '';
    }
  }
  return [...selected.values()];
}
function callContext(text, offset) {
  const tokens = tokenize(text.slice(0, offset)).filter(t => !['comment', 'string'].includes(t.kind));
  const stack = [];
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (['(', '[', '{'].includes(t.value)) stack.push({value: t.value, token: i, argument: 0});
    else if ([')', ']', '}'].includes(t.value)) stack.pop();
    else if (t.value === ',' && stack.length) stack[stack.length - 1].argument++;
  }
  for (let i = stack.length - 1; i >= 0; i--) {
    const frame = stack[i];
    if (frame.value !== '(') continue;
    let before = frame.token - 1;
    if (tokens[before]?.value === ']') {
      let depth = 1;
      while (--before >= 0) {
        if (tokens[before].value === ']') depth++;
        if (tokens[before].value === '[' && --depth === 0) {before--; break;}
      }
    }
    if (tokens[before]?.kind !== 'word') continue;
    const name = tokens[before].value;
    const receiver = tokens[before - 1]?.value === '.' ? tokens[before - 2]?.value : undefined;
    return {name, receiver, argument: frame.argument};
  }
}
module.exports = {tokenize, analyze, visibleSymbols, splitParameters, callContext};
