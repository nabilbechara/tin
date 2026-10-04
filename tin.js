// Theme, sidebar tracking, copy buttons, and a tokenizer for Tin code blocks.
(function () {
  var root = document.documentElement;
  var saved = null;
  try { saved = localStorage.getItem('tin-theme'); } catch (e) {}
  if (saved) root.setAttribute('data-theme', saved);
  else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) root.setAttribute('data-theme', 'light');
  window.tinToggleTheme = function () {
    var next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem('tin-theme', next); } catch (e) {}
  };

  var KEYWORDS = ('package import fn let mut const type struct shape enum dyn if else for in match return break continue defer ' +
    'try catch fail keep within limit guard scope arena parallel select detach with use on once secret max shared wrap nil true false').split(' ');
  var TYPES = 'i8 i16 i32 i64 u8 u16 u32 u64 f32 f64 bool str rune fault query Duration Size map'.split(' ');
  var BUILTINS = 'len cap append make copy delete panic keep bound reveal min new print println spawn wait cancel yield after canceled recv send'.split(' ');
  var kw = {}, ty = {}, bi = {};
  KEYWORDS.forEach(function (k) { kw[k] = 1; });
  TYPES.forEach(function (k) { ty[k] = 1; });
  BUILTINS.forEach(function (k) { bi[k] = 1; });

  function esc(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  function span(cls, s) { return '<span class="' + cls + '">' + esc(s) + '</span>'; }

  function str(s) {
    // "..." with {interpolation}: colour the braces and expression separately.
    var out = '', i = 0, buf = '';
    while (i < s.length) {
      var c = s[i];
      if (c === '\\') { buf += c + (s[i + 1] || ''); i += 2; continue; }
      if (c === '{' && s[i + 1] === '{') { buf += '{{'; i += 2; continue; }
      if (c === '}' && s[i + 1] === '}') { buf += '}}'; i += 2; continue; }
      if (c === '{') {
        var j = s.indexOf('}', i);
        if (j < 0) { buf += c; i++; continue; }
        out += span('tok-s', buf); buf = '';
        out += span('tok-i', s.slice(i, j + 1));
        i = j + 1; continue;
      }
      buf += c; i++;
    }
    return out + span('tok-s', buf);
  }

  function highlight(src) {
    var out = '', i = 0, n = src.length;
    var ident = /[A-Za-z_][A-Za-z0-9_]*/y;
    var num = /(0x[0-9a-fA-F_]+|0b[01_]+|0o[0-7_]+|[0-9][0-9_]*(\.[0-9_]+)?([eE][+-]?[0-9]+)?)(ns|us|ms|s|m|h|kb|mb|gb|b)?\b/y;
    while (i < n) {
      var c = src[i];
      if (c === '/' && src[i + 1] === '/') { var e = src.indexOf('\n', i); if (e < 0) e = n; out += span('tok-c', src.slice(i, e)); i = e; continue; }
      if (c === '"') { var j = i + 1; while (j < n && src[j] !== '"') { if (src[j] === '\\') j++; j++; } out += str(src.slice(i, j + 1)); i = j + 1; continue; }
      if (c === '`') { var k = src.indexOf('`', i + 1); if (k < 0) k = n - 1; out += span('tok-s', src.slice(i, k + 1)); i = k + 1; continue; }
      if (c === "'") { var q = src.indexOf("'", i + 2); if (src[i + 1] === '\\') q = src.indexOf("'", i + 3); if (q < 0) q = i + 2; out += span('tok-s', src.slice(i, q + 1)); i = q + 1; continue; }
      if (c === '@') { ident.lastIndex = i + 1; var am = ident.exec(src); if (am) { out += span('tok-a', '@' + am[0]); i = ident.lastIndex; continue; } }
      num.lastIndex = i;
      if (/[0-9]/.test(c)) { var nm = num.exec(src); if (nm) { out += span('tok-n', nm[0]); i = num.lastIndex; continue; } }
      ident.lastIndex = i;
      if (/[A-Za-z_]/.test(c)) {
        var m = ident.exec(src), w = m[0], after = src.slice(ident.lastIndex, ident.lastIndex + 1);
        var before = out.slice(-60);
        if (kw[w]) out += span('tok-k', w);
        else if (ty[w]) out += span('tok-t', w);
        else if (/^[A-Z]/.test(w) && after !== '(' && !/\.$/.test(src.slice(0, i))) out += span('tok-t', w);
        else if (after === '(' || after === '[') out += span((bi[w] ? 'tok-b' : 'tok-f'), w);
        else out += esc(w);
        i = ident.lastIndex; continue;
      }
      if (/[=+\-*\/%<>!&|^~?:.]/.test(c)) { out += span('tok-o', c); i++; continue; }
      out += esc(c); i++;
    }
    return out;
  }

  function ready() {
    // On phones the contents panel starts closed.
    var toc = document.querySelector('.side .toc');
    if (toc && window.innerWidth <= 900) toc.open = false;
    var blocks = document.querySelectorAll('pre code.tin');
    for (var b = 0; b < blocks.length; b++) {
      var el = blocks[b], text = el.textContent;
      el.innerHTML = highlight(text);
      var btn = document.createElement('button');
      btn.className = 'copy'; btn.textContent = 'copy';
      btn.setAttribute('data-src', text);
      btn.addEventListener('click', function (ev) {
        var t = ev.currentTarget;
        try { navigator.clipboard.writeText(t.getAttribute('data-src')); t.textContent = 'copied'; setTimeout(function () { t.textContent = 'copy'; }, 1200); } catch (e) {}
      });
      el.parentNode.appendChild(btn);
    }
    // Sidebar: mark the section in view.
    var links = document.querySelectorAll('.side a[href^="#"]');
    if (links.length && 'IntersectionObserver' in window) {
      var map = {};
      links.forEach(function (a) { map[a.getAttribute('href').slice(1)] = a; });
      var current = null;
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (en.isIntersecting) {
            var a = map[en.target.id]; if (!a) return;
            if (current) current.classList.remove('active');
            current = a; a.classList.add('active');
          }
        });
      }, { rootMargin: '-70px 0px -70% 0px', threshold: 0 });
      Object.keys(map).forEach(function (id) { var t = document.getElementById(id); if (t) io.observe(t); });
    }
    // Open the deeper block of a hash target.
    function openHash() {
      var id = location.hash.slice(1); if (!id) return;
      var t = document.getElementById(id); if (!t) return;
      var d = t.closest('details'); if (d) d.open = true;
    }
    window.addEventListener('hashchange', openHash); openHash();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready); else ready();
})();
