#!/usr/bin/env python3
"""Converts the compiler's untyped word dialect (fn/let/while, untyped parameters, C-string literals) into
typed edition 1 written with i64 words, for trusted files (toolchain/compiler/, the runtime).

    python3 tools/dev/legacy2tin.py [--analyze FILE]... FILE...

Each FILE is rewritten in place. A function's result is i64 when any `return value` appears in it (void
otherwise); `--analyze` files are read only, to learn the results of the functions they define. Conditions
become booleans (`x != 0`), comparisons used as values become `i64(a < b)`, string literals become
`cstr("...")` (the address of the literal's bytes: the C string the untyped records hold), `load8` results
are widened with `i64(...)`, `let` becomes `mut` for variables that are assigned or whose address is taken,
an assigned parameter is copied into a mutable local, and reserved words used as names get a trailing
underscore. Comments and blank lines are kept. It is a one-time migration tool (#228): the typed data
model replaces the words step by step afterwards.
"""
import os
import re
import sys

RESERVED = {"enum", "match", "within", "limit", "guard", "parallel", "detach", "secret", "shared", "fail", "catch", "keep",
            "use", "on", "scope", "spawn", "select", "once", "arena", "with", "bind", "reveal", "dyn", "shape", "in", "lane",
            "loop", "ref", "move", "new", "unit", "wrap", "yield", "len", "cap", "copy", "append", "delete", "make", "print",
            "println", "min", "max", "clear", "panic", "cast", "str", "bool", "i64", "u64", "i32", "u32", "i16", "u16", "i8", "u8",
            "f32", "f64"}
# names the parser reads as language words when they start a statement or follow certain tokens
KEYWORDS = {"fn", "extern", "const", "var", "let", "if", "else", "while", "return", "break", "continue"}


class Tok:
    def __init__(self, kind, text, line, start, end, blank_before=0, comments=None):
        self.kind = kind
        self.text = text
        self.line = line
        self.start = start
        self.end = end
        self.comments = comments or []  # leading comment lines (own-line comments before this token)
        self.trail = None  # trailing comment on the same line
        self.blank_before = blank_before


def ends_stmt(t):
    if t.kind in ("id", "num", "chr", "str"):
        if t.kind == "id" and t.text in ("fn", "if", "else", "while", "let", "extern", "const", "var"):
            return False
        return True
    return t.kind == "p" and t.text in (")", "]", "}", "++", "--")


def lex(src):
    toks = []
    i = 0
    n = len(src)
    line = 1
    pending = []
    blank = 0
    last_tok_line = 0
    while i < n:
        c = src[i]
        if c == "\n":
            if toks and last_tok_line == line and ends_stmt(toks[-1]):
                st = Tok("p", ";", line, i, i)
                toks.append(st)
            line += 1
            i += 1
            continue
        if c in " \t\r":
            i += 1
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            if j < 0:
                j = n
            text = src[i:j].rstrip()
            if toks and last_tok_line == line and toks[-1].trail is None and not pending:
                toks[-1].trail = text
            else:
                pending.append((line, text))
            i = j
            continue
        start = i
        if c.isalpha() or c == "_":
            while i < n and (src[i].isalnum() or src[i] == "_"):
                i += 1
            kind = "id"
        elif c.isdigit():
            if src.startswith("0x", i) or src.startswith("0X", i):
                i += 2
                while i < n and (src[i] in "0123456789abcdefABCDEF_"):
                    i += 1
            elif src.startswith("0b", i):
                i += 2
                while i < n and src[i] in "01_":
                    i += 1
            else:
                while i < n and (src[i].isdigit() or src[i] == "_"):
                    i += 1
            kind = "num"
        elif c == "'":
            i += 1
            while src[i] != "'":
                if src[i] == "\\":
                    i += 1
                i += 1
            i += 1
            kind = "chr"
        elif c == '"':
            i += 1
            while src[i] != '"':
                if src[i] == "\\":
                    i += 1
                i += 1
            i += 1
            kind = "str"
        else:
            three = src[i:i + 3]
            two = src[i:i + 2]
            if three in ("<<=", ">>=", "..."):
                i += 3
            elif two in ("==", "!=", "<=", ">=", "&&", "||", "<<", ">>", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "++", "--"):
                i += 2
            else:
                i += 1
            kind = "p"
        t = Tok(kind, src[start:i], line, start, i)
        t.comments = pending
        pending = []
        toks.append(t)
        last_tok_line = line
    t = Tok("eof", "", line, n, n)
    t.comments = pending
    toks.append(t)
    return toks


# ---------------------------------------------------------------- AST

class N:
    def __init__(self, kind, **kw):
        self.kind = kind
        self.__dict__.update(kw)


class Parser:
    def __init__(self, toks, src, name):
        self.t = toks
        self.i = 0
        self.src = src
        self.name = name

    def peek(self, k=0):
        return self.t[min(self.i + k, len(self.t) - 1)]

    def next(self):
        t = self.t[self.i]
        self.i += 1
        return t

    def is_(self, text, k=0):
        t = self.peek(k)
        return t.text == text and t.kind in ("p", "id")

    def expect(self, text):
        t = self.next()
        if t.text != text:
            raise SyntaxError(f"{self.name}:{t.line}: expected {text!r}, found {t.text!r}")
        return t

    def ident(self):
        t = self.next()
        if t.kind != "id":
            raise SyntaxError(f"{self.name}:{t.line}: expected identifier, found {t.text!r}")
        return t

    # top level
    def program(self):
        decls = []
        while self.peek().kind != "eof":
            if self.is_(";"):
                self.next()
                continue
            decls.append(self.decl())
        self.tail_comments = self.peek().comments
        return decls

    def decl(self):
        t = self.peek()
        lead = t.comments
        line = t.line
        first_line = lead[0][0] if lead else t.line
        if self.is_("fn"):
            d = self.fn(False)
        elif self.is_("extern"):
            self.next()
            d = self.fn(True)
        elif self.is_("const"):
            self.next()
            name = self.ident()
            self.expect("=")
            e = self.expr()
            d = N("const", name=name.text, value=e)
            self.end(d)
        elif self.is_("var"):
            self.next()
            name = self.ident()
            init = None
            if self.is_("="):
                self.next()
                init = self.expr()
            d = N("var", name=name.text, init=init)
            self.end(d)
        else:
            raise SyntaxError(f"{self.name}:{t.line}: unexpected {t.text!r} at top level")
        d.lead = lead
        d.line = line
        d.first_line = first_line
        d.last_line = self.t[self.i - 1].line
        return d

    def end(self, node):
        last = self.peek(-1)
        if self.is_("}"):
            node.trail = last.trail
            return
        self.expect(";")
        node.trail = self.t[self.i - 1].trail or last.trail

    def fn(self, ext):
        self.expect("fn")
        name = self.ident().text
        self.expect("(")
        params = []
        variadic = False
        while not self.is_(")"):
            if self.is_("..."):
                self.next()
                variadic = True
            else:
                params.append(self.ident().text)
            if self.is_(","):
                self.next()
        self.expect(")")
        if ext:
            self.expect(";")
            return N("extern", name=name, params=params, variadic=variadic)
        body = self.block()
        return N("fn", name=name, params=params, body=body)

    def block(self):
        self.expect("{")
        stmts = []
        while not self.is_("}"):
            if self.is_(";"):
                self.next()
                continue
            stmts.append(self.stmt())
        close = self.expect("}")
        return N("block", stmts=stmts, close_comments=close.comments, trail=close.trail)

    def stmt(self):
        t = self.peek()
        lead = t.comments
        line = t.line
        s = self.stmt1()
        s.lead = lead
        s.line = line
        s.first_line = lead[0][0] if lead else line
        s.last_line = self.t[self.i - 1].line
        return s

    def stmt1(self):
        if self.is_("let"):
            self.next()
            name = self.ident().text
            init = None
            if self.is_("="):
                self.next()
                init = self.expr()
            s = N("let", name=name, init=init)
            self.end(s)
            return s
        if self.is_("if"):
            return self.if_()
        if self.is_("while"):
            self.next()
            cond = self.expr()
            body = self.block()
            return N("while", cond=cond, body=body, trail=None)
        if self.is_("return"):
            self.next()
            e = None
            if not self.is_(";"):
                e = self.expr()
            s = N("return", value=e)
            self.end(s)
            return s
        if self.is_("break"):
            self.next()
            s = N("break")
            self.end(s)
            return s
        if self.is_("continue"):
            self.next()
            s = N("continue")
            self.end(s)
            return s
        if self.is_("{"):
            b = self.block()
            return N("bare", body=b)
        e = self.expr()
        if self.peek().text in ("=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>="):
            op = self.next().text
            v = self.expr()
            s = N("assign", target=e, op=op, value=v)
            self.end(s)
            return s
        if self.peek().text in ("++", "--"):
            op = self.next().text
            s = N("assign", target=e, op=op[0] + "=", value=N("num", text="1"))
            self.end(s)
            return s
        s = N("expr", value=e)
        self.end(s)
        return s

    def if_(self):
        self.expect("if")
        cond = self.expr()
        then = self.block()
        els = None
        if self.is_("else"):
            self.next()
            if self.is_("if"):
                els = self.if_()
                els.lead = []
                els.line = 0
            else:
                els = self.block()
        return N("if", cond=cond, then=then, els=els)

    # expressions
    PREC = {"||": 1, "&&": 2, "==": 3, "!=": 3, "<": 3, "<=": 3, ">": 3, ">=": 3,
            "+": 4, "-": 4, "|": 4, "^": 4, "*": 5, "/": 5, "%": 5, "<<": 5, ">>": 5, "&": 5}

    def expr(self, minp=1):
        left = self.unary()
        while True:
            t = self.peek()
            p = self.PREC.get(t.text) if t.kind == "p" else None
            if p is None or p < minp:
                return left
            self.next()
            right = self.expr(p + 1)
            left = N("bin", op=t.text, l=left, r=right)

    def unary(self):
        t = self.peek()
        if t.kind == "p" and t.text in ("-", "!", "~", "&", "*"):
            self.next()
            x = self.unary()
            return N("un", op=t.text, x=x)
        return self.postfix()

    def postfix(self):
        e = self.primary()
        while True:
            if self.is_("("):
                self.next()
                args = []
                while not self.is_(")"):
                    args.append(self.expr())
                    if self.is_(","):
                        self.next()
                self.expect(")")
                e = N("call", fn=e, args=args)
            elif self.is_("["):
                self.next()
                i = self.expr()
                self.expect("]")
                e = N("index", x=e, i=i)
            else:
                return e

    def primary(self):
        t = self.next()
        if t.kind == "num":
            return N("num", text=t.text)
        if t.kind == "chr":
            return N("chr", text=t.text)
        if t.kind == "str":
            return N("str", text=t.text)
        if t.kind == "id":
            return N("id", name=t.text)
        if t.text == "(":
            e = self.expr()
            self.expect(")")
            return N("paren", x=e)
        raise SyntaxError(f"{self.name}:{t.line}: unexpected {t.text!r} in expression")


# ---------------------------------------------------------------- analysis

def walk_exprs(node, f):
    if node is None:
        return
    k = node.kind
    if k in ("num", "chr", "str", "id"):
        f(node)
    elif k == "paren":
        f(node)
        walk_exprs(node.x, f)
    elif k == "un":
        f(node)
        walk_exprs(node.x, f)
    elif k == "bin":
        f(node)
        walk_exprs(node.l, f)
        walk_exprs(node.r, f)
    elif k == "call":
        f(node)
        walk_exprs(node.fn, f)
        for a in node.args:
            walk_exprs(a, f)
    elif k == "index":
        f(node)
        walk_exprs(node.x, f)
        walk_exprs(node.i, f)


def walk_stmts(block, f):
    for s in block.stmts:
        f(s)
        if s.kind == "if":
            x = s
            while x is not None:
                walk_stmts(x.then, f)
                if x.els is not None and x.els.kind == "if":
                    x = x.els
                    f(x)
                    continue
                if x.els is not None:
                    walk_stmts(x.els, f)
                x = None
        elif s.kind == "while":
            walk_stmts(s.body, f)
        elif s.kind == "bare":
            walk_stmts(s.body, f)


def stmt_exprs(s):
    k = s.kind
    if k == "let":
        return [s.init]
    if k == "assign":
        return [s.target, s.value]
    if k == "return":
        return [s.value]
    if k == "expr":
        return [s.value]
    if k == "if":
        return [s.cond]
    if k == "while":
        return [s.cond]
    return []


def lvalue_root(e):
    while e.kind in ("index", "paren"):
        e = e.x
    return e.name if e.kind == "id" else None


INTRINSICS_LOAD = {"load8"}


class Conv:
    def __init__(self, funcs_ret, known_fns):
        self.ret = funcs_ret  # name -> True when the function returns a value
        self.known = known_fns
        self.out = []
        self.warnings = []

    def rename(self, name):
        if name in RESERVED:
            return name + "_"
        return name

    # --- expression emission: returns (text, kind, prec) with kind 'w' or 'b'
    def lit_num(self, text):
        t = text.replace("_", "")
        v = int(t, 0)
        if v >= 1 << 63:
            v -= 1 << 64
            if v == -(1 << 63):
                return "(-9223372036854775807 - 1)", 6
            return f"({v})", 6
        return text, 6

    def str_lit(self, text):
        body = text[1:-1]
        body = body.replace("{", "{{").replace("}", "}}")
        return f'cstr("{body}")'

    def expr(self, e, want):
        text, kind, prec = self.ex(e)
        if want == "b" and kind == "w":
            if prec < 4 or prec == 100:
                text = f"({text})"
            return f"{text} != 0", 3
        if want == "w" and kind == "b":
            return f"i64({text})", 6
        return text, prec

    def sub(self, e, want, minprec):
        text, prec = self.expr(e, want)
        if prec < minprec:
            return f"({text})"
        return text

    def ex(self, e):
        k = e.kind
        if k == "num":
            t, p = self.lit_num(e.text)
            return t, "w", p
        if k == "chr":
            return e.text, "w", 6
        if k == "str":
            return self.str_lit(e.text), "w", 6
        if k == "id":
            return self.rename(e.name), "w", 6
        if k == "paren":
            text, kind, prec = self.ex(e.x)
            if prec < 6:
                return f"({text})", kind, 6
            return text, kind, prec
        if k == "un":
            if e.op == "!":
                text, prec = self.expr(e.x, "b")
                xk = self.ex(e.x)[1]
                if xk == "w":
                    # !x on a word is x == 0
                    t2, p2 = self.expr(e.x, "w")
                    if p2 < 4:
                        t2 = f"({t2})"
                    return f"{t2} == 0", "b", 3
                if prec < 6:
                    text = f"({text})"
                return f"!{text}", "b", 6
            if e.op == "&":
                inner = self.sub(e.x, "w", 6)
                return f"&{inner}", "w", 6
            if e.op == "*":
                inner = self.sub(e.x, "w", 6)
                return f"{inner}[0]", "w", 6
            inner = self.sub(e.x, "w", 6)
            return f"{e.op}{inner}", "w", 6
        if k == "bin":
            op = e.op
            p = Parser.PREC[op]
            if op in ("&&", "||"):
                l = self.sub(e.l, "b", p)
                r = self.sub(e.r, "b", p + 1)
                return f"{l} {op} {r}", "b", p
            l = self.sub(e.l, "w", p)
            r = self.sub(e.r, "w", p + 1)
            kind = "b" if op in ("==", "!=", "<", "<=", ">", ">=") else "w"
            return f"{l} {op} {r}", kind, p
        if k == "call":
            if e.fn.kind != "id":
                raise ValueError("indirect call")
            name = e.fn.name
            args = [self.expr(a, "w")[0] for a in e.args]
            if name == "load8":
                return f"i64(load8({args[0]}))", "w", 6
            return f"{self.rename(name)}({', '.join(args)})", "w", 6
        if k == "index":
            x = self.sub(e.x, "w", 6)
            i = self.expr(e.i, "w")[0]
            return f"{x}[{i}]", "w", 6
        raise ValueError(f"expr kind {k}")


def is_int_expr_const(e):
    return e.kind == "num"


def convert(path, src):
    name = os.path.basename(path)
    toks = lex(src)
    p = Parser(toks, src, name)
    decls = p.program()
    # function results
    funcs_ret = {}
    known = set()
    for d in decls:
        if d.kind == "fn":
            known.add(d.name)
            has = [False]

            def sf(s):
                if s.kind == "return" and s.value is not None:
                    has[0] = True
            walk_stmts(d.body, sf)
            funcs_ret[d.name] = has[0]
        elif d.kind == "extern":
            known.add(d.name)
            funcs_ret[d.name] = True
    return decls, p, funcs_ret, known


def emit_file(decls, parser, funcs_ret, global_ret, global_assigned_params=None):
    c = Conv(global_ret, set())
    out = []

    def comments(lines, indent):
        for _, text in lines:
            out.append("\t" * indent + text)

    def ind(n):
        return "\t" * n

    def blank_gap(prev_line, line):
        return prev_line is not None and line - prev_line > 1

    def emit_block(b, indent, fn_info):
        prev_end = None
        for s in b.stmts:
            if prev_end is not None and s.first_line - prev_end > 1:
                out.append("")
            emit_stmt(s, indent, fn_info)
            prev_end = s.last_line
        comments(b.close_comments, indent)

    def trail(t):
        return f" {t}" if t else ""

    def cond_text(e):
        return c.expr(e, "b")[0]

    def emit_stmt(s, indent, fi):
        comments(s.lead, indent)
        k = s.kind
        i = ind(indent)
        if k == "let":
            kw = "mut" if s.name in fi["mut_locals"] else "let"
            nm = c.rename(s.name)
            if s.init is None:
                out.append(f"{i}{kw} {nm} i64{trail(s.trail)}" if kw == "mut" else f"{i}mut {nm} i64{trail(s.trail)}")
            else:
                out.append(f"{i}{kw} {nm} = {c.expr(s.init, 'w')[0]}{trail(s.trail)}")
        elif k == "assign":
            tgt = c.expr(s.target, "w")[0]
            # a parameter that is assigned is renamed to a local copy
            val = c.expr(s.value, "w")[0]
            out.append(f"{i}{tgt} {s.op} {val}{trail(s.trail)}")
        elif k == "return":
            if s.value is None:
                out.append(f"{i}return 0{trail(s.trail)}" if fi["ret"] else f"{i}return{trail(s.trail)}")
            else:
                out.append(f"{i}return {c.expr(s.value, 'w')[0]}{trail(s.trail)}")
        elif k == "break":
            out.append(f"{i}break{trail(s.trail)}")
        elif k == "continue":
            out.append(f"{i}continue{trail(s.trail)}")
        elif k == "expr":
            text = c.expr(s.value, "w")[0]
            out.append(f"{i}{text}{trail(s.trail)}")
        elif k == "while":
            cond = s.cond
            if cond.kind == "num" and cond.text == "1":
                out.append(f"{i}for {{")
            else:
                out.append(f"{i}for {cond_text(cond)} {{")
            emit_block(s.body, indent + 1, fi)
            out.append(f"{i}}}")
        elif k == "bare":
            out.append(f"{i}{{")
            emit_block(s.body, indent + 1, fi)
            out.append(f"{i}}}")
        elif k == "if":
            emit_if(s, indent, fi, False)
        else:
            raise ValueError(k)

    def emit_if(s, indent, fi, is_else):
        i = ind(indent)
        head = f"if {cond_text(s.cond)} {{"
        out.append(("} else " + head) if is_else else (i + head))
        emit_block(s.then, indent + 1, fi)
        if s.els is None:
            out.append(f"{i}}}")
        elif s.els.kind == "if":
            comments(getattr(s.els, "lead", []), indent)
            # else if: continue the chain
            out_idx = len(out)
            emit_if_chain(s.els, indent, fi)
        else:
            out.append(f"{i}}} else {{")
            emit_block(s.els, indent + 1, fi)
            out.append(f"{i}}}")

    def emit_if_chain(s, indent, fi):
        i = ind(indent)
        out.append(f"{i}}} else if {cond_text(s.cond)} {{")
        emit_block(s.then, indent + 1, fi)
        if s.els is None:
            out.append(f"{i}}}")
        elif s.els.kind == "if":
            emit_if_chain(s.els, indent, fi)
        else:
            out.append(f"{i}}} else {{")
            emit_block(s.els, indent + 1, fi)
            out.append(f"{i}}}")

    prev_line = None
    prev_kind = None
    if parser.name == "util.tin":
        out.append("// cstr is the address of a string literal's bytes: the untyped C-string word the compiler's records hold.")
        out.append("fn cstr(s str) i64 {")
        out.append("\treturn cast(i64, s) + 8")
        out.append("}")
        out.append("")
    for d in decls:
        if prev_line is not None and d.first_line - prev_line > 1:
            out.append("")
        elif prev_line is not None and (d.kind in ("fn",) or prev_kind == "fn"):
            out.append("")
        comments(d.lead, 0)
        prev_line = d.last_line
        prev_kind = d.kind
        k = d.kind
        if k == "const":
            text = c.expr(d.value, "w")[0]
            out.append(f"const {c.rename(d.name)} = {text}{trail(d.trail)}")
        elif k == "var":
            if d.init is not None:
                out.append(f"shared mut {c.rename(d.name)} i64 = {c.expr(d.init, 'w')[0]}{trail(d.trail)}")
            else:
                out.append(f"shared mut {c.rename(d.name)} i64{trail(d.trail)}")
        elif k == "extern":
            ps = [f"{c.rename(x)} i64" for x in d.params]
            if d.variadic:
                ps.append("...")
            out.append(f"extern fn {d.name}({', '.join(ps)}) i64{trail(None)}")
        elif k == "fn":
            fi = analyze_fn(d, global_ret)
            ps = []
            pre = []
            for x in d.params:
                if x in fi["assigned_params"]:
                    ps.append(f"{c.rename(x)}_in i64")
                    pre.append(f"\tmut {c.rename(x)} = {c.rename(x)}_in")
                else:
                    ps.append(f"{c.rename(x)} i64")
            res = " i64" if fi["ret"] else ""
            out.append(f"fn {c.rename(d.name)}({', '.join(ps)}){res} {{")
            out.extend(pre)
            emit_block(d.body, 1, fi)
            if fi["ret"] and d.body.stmts and d.body.stmts[-1].kind in ("expr", "let", "assign", "break", "continue"):
                out.append("\treturn 0")
            elif fi["ret"] and d.body.stmts and d.body.stmts[-1].kind == "if":
                last = d.body.stmts[-1]
                # an if chain without a final else, or one that does not return everywhere
                def all_return(x):
                    if x is None or x.kind != "if" and x.kind != "block":
                        return False
                    if x.kind == "block":
                        return bool(x.stmts) and x.stmts[-1].kind == "return" or (bool(x.stmts) and x.stmts[-1].kind == "if" and all_return(x.stmts[-1]))
                    return x.els is not None and all_return(x.then) and (all_return(x.els) if x.els.kind in ("if", "block") else False)
                if not all_return(last):
                    out.append("\treturn 0")
            out.append("}")
    comments(parser.tail_comments, 0)
    return "\n".join(out) + "\n"


def analyze_fn(d, global_ret):
    assigned = set()
    addr = set()
    declared = set()

    def sf(s):
        if s.kind == "assign":
            r = lvalue_root(s.target)
            if r and s.target.kind == "id":
                assigned.add(r)
        if s.kind == "let":
            declared.add(s.name)
        for e in stmt_exprs(s):
            if e is not None:
                walk_exprs(e, lambda x: addr.add(x.x.name) if x.kind == "un" and x.op == "&" and x.x.kind == "id" else None)
    walk_stmts(d.body, sf)
    params = set(d.params)
    # a let whose name is assigned later (or whose address is taken) is mutable
    mut_locals = {n for n in declared if n in assigned or n in addr}
    assigned_params = {n for n in params if n in assigned or n in addr}
    return {"mut_locals": mut_locals, "assigned_params": assigned_params, "ret": global_ret.get(d.name, False)}


def main():
    args = sys.argv[1:]
    analyze = []
    files = []
    i = 0
    while i < len(args):
        if args[i] == "--analyze":
            analyze.append(args[i + 1])
            i += 2
        else:
            files.append(args[i])
            i += 1
    parsed = []
    global_ret = {}
    for f in analyze:
        decls, p, fr, known = convert(f, open(f).read())
        global_ret.update(fr)
    for f in files:
        decls, p, fr, known = convert(f, open(f).read())
        parsed.append((f, decls, p))
        global_ret.update(fr)
    for f, decls, p in parsed:
        text = emit_file(decls, p, None, global_ret)
        open(f, "w").write(text)
        print("converted", f)


if __name__ == "__main__":
    main()
