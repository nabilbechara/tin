package main

import "fmt"

// Binding power of each binary operator (Go's precedence levels).
var binPrec = map[string]int{
	"||": 1,
	"&&": 2,
	"==": 3, "!=": 3, "<": 3, "<=": 3, ">": 3, ">=": 3,
	"+": 4, "-": 4, "|": 4, "^": 4,
	"*": 5, "/": 5, "%": 5, "<<": 5, ">>": 5, "&": 5,
}

type parser struct {
	toks []Token
	i    int
}

type parseFailure struct{ err *CompileError }

// Parse appends one file's declarations to prog; it stops at the first syntax error.
func Parse(toks []Token, prog *Program) (err error) {
	p := &parser{toks: toks}
	defer func() {
		if r := recover(); r != nil {
			f, ok := r.(parseFailure)
			if !ok {
				panic(r)
			}
			err = f.err
		}
	}()
	for p.peek().Kind != TokEOF {
		switch {
		case p.is("fn"):
			prog.Fns = append(prog.Fns, p.parseFn(false))
		case p.is("extern"):
			p.next()
			prog.Fns = append(prog.Fns, p.parseFn(true))
		case p.is("const"):
			pos := p.next().Pos
			name := p.expectIdent().Text
			p.expect("=")
			init := p.parseExpr(1)
			p.expect(";")
			prog.Consts = append(prog.Consts, &ConstDecl{P: pos, Name: name, Init: init})
		case p.is("var"):
			pos := p.next().Pos
			name := p.expectIdent().Text
			var init Expr
			if p.is("=") {
				p.next()
				init = p.parseExpr(1)
			}
			p.expect(";")
			prog.Vars = append(prog.Vars, &VarDecl{P: pos, Name: name, Init: init})
		default:
			p.fail(p.peek().Pos, "expected a declaration (fn, extern, const, var), found %s", describe(p.peek()))
		}
	}
	return nil
}

func (p *parser) peek() Token { return p.toks[p.i] }

func (p *parser) next() Token {
	t := p.toks[p.i]
	if t.Kind != TokEOF {
		p.i++
	}
	return t
}

// is reports whether the next token is the given keyword or punctuation.
func (p *parser) is(text string) bool {
	t := p.peek()
	return (t.Kind == TokKeyword || t.Kind == TokPunct) && t.Text == text
}

func (p *parser) expect(text string) Token {
	if !p.is(text) {
		p.fail(p.peek().Pos, "expected '%s', found %s", text, describe(p.peek()))
	}
	return p.next()
}

func (p *parser) expectIdent() Token {
	if p.peek().Kind != TokIdent {
		p.fail(p.peek().Pos, "expected a name, found %s", describe(p.peek()))
	}
	return p.next()
}

func (p *parser) fail(pos Pos, format string, args ...any) {
	panic(parseFailure{&CompileError{Pos: pos, Msg: fmt.Sprintf(format, args...)}})
}

func describe(t Token) string {
	switch t.Kind {
	case TokEOF:
		return "end of file"
	case TokIdent:
		return fmt.Sprintf("name '%s'", t.Text)
	case TokInt:
		return "a number"
	case TokString:
		return "a string"
	}
	return fmt.Sprintf("'%s'", t.Text)
}

func (p *parser) parseFn(extern bool) *FnDecl {
	pos := p.expect("fn").Pos
	fn := &FnDecl{P: pos, Name: p.expectIdent().Text, Extern: extern}
	p.expect("(")
	if !p.is(")") {
		for {
			fn.Params = append(fn.Params, p.expectIdent().Text)
			if !p.is(",") {
				break
			}
			p.next()
		}
	}
	p.expect(")")
	if extern {
		p.expect(";")
		return fn
	}
	fn.Body = p.parseBlock()
	return fn
}

func (p *parser) parseBlock() *Block {
	b := &Block{P: p.expect("{").Pos}
	for !p.is("}") {
		if p.peek().Kind == TokEOF {
			p.fail(p.peek().Pos, "expected '}', found end of file")
		}
		b.Stmts = append(b.Stmts, p.parseStmt())
	}
	p.next()
	return b
}

func (p *parser) parseStmt() Stmt {
	pos := p.peek().Pos
	switch {
	case p.is("let"):
		p.next()
		name := p.expectIdent().Text
		p.expect("=")
		init := p.parseExpr(1)
		p.expect(";")
		return &LetStmt{P: pos, Name: name, Init: init}
	case p.is("if"):
		return p.parseIf()
	case p.is("while"):
		p.next()
		cond := p.parseExpr(1)
		return &WhileStmt{P: pos, Cond: cond, Body: p.parseBlock()}
	case p.is("return"):
		p.next()
		var v Expr
		if !p.is(";") {
			v = p.parseExpr(1)
		}
		p.expect(";")
		return &ReturnStmt{P: pos, Value: v}
	case p.is("break"):
		p.next()
		p.expect(";")
		return &BreakStmt{P: pos}
	case p.is("continue"):
		p.next()
		p.expect(";")
		return &ContinueStmt{P: pos}
	case p.is("{"):
		return p.parseBlock()
	}
	x := p.parseExpr(1)
	if p.is("=") {
		p.next()
		v := p.parseExpr(1)
		p.expect(";")
		return &AssignStmt{P: pos, Target: x, Value: v}
	}
	p.expect(";")
	return &ExprStmt{P: pos, X: x}
}

func (p *parser) parseIf() *IfStmt {
	s := &IfStmt{P: p.expect("if").Pos}
	s.Cond = p.parseExpr(1)
	s.Then = p.parseBlock()
	if p.is("else") {
		p.next()
		if p.is("if") {
			s.Else = p.parseIf()
		} else {
			s.Else = p.parseBlock()
		}
	}
	return s
}

// parseExpr is a precedence-climbing parser for left-associative binary operators.
func (p *parser) parseExpr(minPrec int) Expr {
	left := p.parseUnary()
	for {
		t := p.peek()
		prec, ok := binPrec[t.Text]
		if t.Kind != TokPunct || !ok || prec < minPrec {
			return left
		}
		p.next()
		right := p.parseExpr(prec + 1)
		left = &Binary{P: t.Pos, Op: t.Text, L: left, R: right}
	}
}

func (p *parser) parseUnary() Expr {
	t := p.peek()
	if t.Kind == TokPunct && (t.Text == "-" || t.Text == "!" || t.Text == "~" || t.Text == "&") {
		p.next()
		return &Unary{P: t.Pos, Op: t.Text, X: p.parseUnary()}
	}
	return p.parsePostfix()
}

func (p *parser) parsePostfix() Expr {
	x := p.parsePrimary()
	for {
		switch {
		case p.is("("):
			id, ok := x.(*Ident)
			if !ok {
				p.fail(p.peek().Pos, "only named functions can be called")
			}
			p.next()
			call := &Call{P: id.P, Name: id.Name}
			if !p.is(")") {
				for {
					call.Args = append(call.Args, p.parseExpr(1))
					if !p.is(",") {
						break
					}
					p.next()
				}
			}
			p.expect(")")
			x = call
		case p.is("["):
			pos := p.next().Pos
			i := p.parseExpr(1)
			p.expect("]")
			x = &Index{P: pos, X: x, I: i}
		default:
			return x
		}
	}
}

func (p *parser) parsePrimary() Expr {
	t := p.next()
	switch t.Kind {
	case TokInt:
		return &IntLit{P: t.Pos, Val: t.Val}
	case TokString:
		return &StrLit{P: t.Pos, Val: t.Text}
	case TokIdent:
		return &Ident{P: t.Pos, Name: t.Text}
	case TokPunct:
		if t.Text == "(" {
			x := p.parseExpr(1)
			p.expect(")")
			return x
		}
	}
	p.fail(t.Pos, "expected an expression, found %s", describe(t))
	return nil
}
