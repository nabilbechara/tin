package main

import "fmt"

// Builtins compiled inline, with their argument counts.
var intrinsics = map[string]int{"load8": 1, "store8": 2}

const maxParams = 8 // arguments are passed in x0..x7

type checker struct {
	globals map[string]*Symbol
	scopes  []map[string]*Symbol
	fn      *FnDecl
	loops   int
	errs    ErrorList
}

// Check resolves every name, assigns frame slots and evaluates constants.
func Check(prog *Program) error {
	c := &checker{globals: map[string]*Symbol{}}
	for _, fn := range prog.Fns {
		if len(fn.Params) > maxParams {
			c.errorf(fn.P, "function '%s' has %d parameters, the limit is %d", fn.Name, len(fn.Params), maxParams)
		}
		c.declareGlobal(&Symbol{Kind: SymFunc, Name: fn.Name, Pos: fn.P, Fn: fn})
	}
	for _, cd := range prog.Consts {
		c.declareGlobal(&Symbol{Kind: SymConst, Name: cd.Name, Pos: cd.P})
	}
	for _, vd := range prog.Vars {
		c.declareGlobal(&Symbol{Kind: SymGlobal, Name: vd.Name, Pos: vd.P})
	}
	for _, cd := range prog.Consts {
		v, _ := c.constValue(cd.Init)
		if s := c.globals[cd.Name]; s != nil && s.Kind == SymConst && s.Pos == cd.P {
			s.Val = v
			s.Done = true
		}
	}
	for _, vd := range prog.Vars {
		if vd.Init != nil {
			vd.Val, _ = c.constValue(vd.Init)
		}
	}
	for _, fn := range prog.Fns {
		if !fn.Extern {
			c.checkFn(fn)
		}
	}
	main := c.globals["main"]
	switch {
	case main == nil || main.Kind != SymFunc:
		c.errorf(Pos{}, "no main function")
	case main.Fn.Extern:
		c.errorf(main.Pos, "main cannot be extern")
	case len(main.Fn.Params) != 0 && len(main.Fn.Params) != 2:
		c.errorf(main.Pos, "main takes no parameters or (argc, argv)")
	}
	if len(c.errs) > 0 {
		return c.errs
	}
	return nil
}

func (c *checker) errorf(pos Pos, format string, args ...any) {
	c.errs = append(c.errs, &CompileError{Pos: pos, Msg: fmt.Sprintf(format, args...)})
}

func (c *checker) declareGlobal(s *Symbol) {
	if _, ok := intrinsics[s.Name]; ok {
		c.errorf(s.Pos, "'%s' is a builtin and cannot be redeclared", s.Name)
		return
	}
	if prev, ok := c.globals[s.Name]; ok {
		c.errorf(s.Pos, "'%s' redeclared (previous declaration at %s)", s.Name, prev.Pos)
		return
	}
	c.globals[s.Name] = s
}

// constValue evaluates a constant expression made of literals, constants and operators.
func (c *checker) constValue(e Expr) (int64, bool) {
	switch e := e.(type) {
	case *IntLit:
		return e.Val, true
	case *Ident:
		s := c.globals[e.Name]
		if s == nil || s.Kind != SymConst {
			c.errorf(e.P, "'%s' is not a constant", e.Name)
			return 0, false
		}
		if !s.Done {
			c.errorf(e.P, "constant '%s' used before its definition", e.Name)
			return 0, false
		}
		e.Ref = s
		return s.Val, true
	case *Unary:
		if e.Op == "&" {
			break
		}
		v, ok := c.constValue(e.X)
		return evalUnary(e.Op, v), ok
	case *Binary:
		l, lok := c.constValue(e.L)
		r, rok := c.constValue(e.R)
		if !lok || !rok {
			return 0, false
		}
		if (e.Op == "/" || e.Op == "%") && r == 0 {
			c.errorf(e.P, "division by zero in constant expression")
			return 0, false
		}
		return evalBinary(e.Op, l, r), true
	}
	c.errorf(e.exprPos(), "expression is not a constant")
	return 0, false
}

func evalUnary(op string, v int64) int64 {
	switch op {
	case "-":
		return -v
	case "~":
		return ^v
	case "!":
		return b2i(v == 0)
	}
	panic("unknown unary operator " + op)
}

// evalBinary matches the ARM64 instructions codegen emits (shift counts wrap at 64).
func evalBinary(op string, l, r int64) int64 {
	switch op {
	case "+":
		return l + r
	case "-":
		return l - r
	case "*":
		return l * r
	case "/":
		return l / r
	case "%":
		return l % r
	case "&":
		return l & r
	case "|":
		return l | r
	case "^":
		return l ^ r
	case "<<":
		return l << (uint64(r) & 63)
	case ">>":
		return l >> (uint64(r) & 63)
	case "==":
		return b2i(l == r)
	case "!=":
		return b2i(l != r)
	case "<":
		return b2i(l < r)
	case "<=":
		return b2i(l <= r)
	case ">":
		return b2i(l > r)
	case ">=":
		return b2i(l >= r)
	case "&&":
		return b2i(l != 0 && r != 0)
	case "||":
		return b2i(l != 0 || r != 0)
	}
	panic("unknown binary operator " + op)
}

func b2i(b bool) int64 {
	if b {
		return 1
	}
	return 0
}

func (c *checker) checkFn(fn *FnDecl) {
	c.fn = fn
	c.loops = 0
	c.scopes = []map[string]*Symbol{{}}
	fn.NumSlots = 0
	for _, p := range fn.Params {
		c.declareLocal(fn.P, p)
	}
	// The body shares the parameters' scope, so `let x` cannot silently hide parameter x.
	c.checkStmts(fn.Body.Stmts)
}

func (c *checker) declareLocal(pos Pos, name string) *Symbol {
	scope := c.scopes[len(c.scopes)-1]
	if prev, ok := scope[name]; ok {
		c.errorf(pos, "'%s' redeclared in this scope (previous declaration at %s)", name, prev.Pos)
	}
	s := &Symbol{Kind: SymLocal, Name: name, Pos: pos, Slot: c.fn.NumSlots}
	c.fn.NumSlots++
	scope[name] = s
	return s
}

func (c *checker) lookup(name string) *Symbol {
	for i := len(c.scopes) - 1; i >= 0; i-- {
		if s, ok := c.scopes[i][name]; ok {
			return s
		}
	}
	return c.globals[name]
}

func (c *checker) checkScoped(b *Block) {
	c.scopes = append(c.scopes, map[string]*Symbol{})
	c.checkStmts(b.Stmts)
	c.scopes = c.scopes[:len(c.scopes)-1]
}

func (c *checker) checkStmts(stmts []Stmt) {
	for _, s := range stmts {
		c.checkStmt(s)
	}
}

func (c *checker) checkStmt(s Stmt) {
	switch s := s.(type) {
	case *LetStmt:
		c.checkExpr(s.Init)
		s.Sym = c.declareLocal(s.P, s.Name)
	case *AssignStmt:
		c.checkExpr(s.Value)
		switch t := s.Target.(type) {
		case *Ident:
			c.checkExpr(t)
			if t.Ref != nil && t.Ref.Kind == SymConst {
				c.errorf(t.P, "cannot assign to constant '%s'", t.Name)
			}
		case *Index:
			c.checkExpr(t)
		default:
			c.errorf(s.P, "cannot assign to this expression")
		}
	case *ExprStmt:
		c.checkExpr(s.X)
	case *IfStmt:
		c.checkExpr(s.Cond)
		c.checkScoped(s.Then)
		switch e := s.Else.(type) {
		case *Block:
			c.checkScoped(e)
		case *IfStmt:
			c.checkStmt(e)
		}
	case *WhileStmt:
		c.checkExpr(s.Cond)
		c.loops++
		c.checkScoped(s.Body)
		c.loops--
	case *ReturnStmt:
		if s.Value != nil {
			c.checkExpr(s.Value)
		}
	case *BreakStmt:
		if c.loops == 0 {
			c.errorf(s.P, "break outside a loop")
		}
	case *ContinueStmt:
		if c.loops == 0 {
			c.errorf(s.P, "continue outside a loop")
		}
	case *Block:
		c.checkScoped(s)
	}
}

func (c *checker) checkExpr(e Expr) {
	switch e := e.(type) {
	case *IntLit, *StrLit:
	case *Ident:
		s := c.lookup(e.Name)
		switch {
		case s == nil:
			c.errorf(e.P, "undefined: %s", e.Name)
		case s.Kind == SymFunc:
			c.errorf(e.P, "function '%s' used as a value", e.Name)
		default:
			e.Ref = s
		}
	case *Unary:
		if e.Op != "&" {
			c.checkExpr(e.X)
			return
		}
		id, ok := e.X.(*Ident)
		if !ok {
			c.errorf(e.P, "'&' needs a variable name")
			c.checkExpr(e.X)
			return
		}
		c.checkExpr(id)
		if id.Ref != nil && id.Ref.Kind == SymConst {
			c.errorf(e.P, "cannot take the address of constant '%s'", id.Name)
		}
	case *Binary:
		c.checkExpr(e.L)
		c.checkExpr(e.R)
	case *Index:
		c.checkExpr(e.X)
		c.checkExpr(e.I)
	case *Call:
		for _, a := range e.Args {
			c.checkExpr(a)
		}
		if n, ok := intrinsics[e.Name]; ok {
			e.Intrinsic = true
			if len(e.Args) != n {
				c.errorf(e.P, "%s expects %d arguments, got %d", e.Name, n, len(e.Args))
			}
			return
		}
		s := c.lookup(e.Name)
		switch {
		case s == nil:
			c.errorf(e.P, "undefined function: %s", e.Name)
		case s.Kind != SymFunc:
			c.errorf(e.P, "'%s' is not a function", e.Name)
		case len(e.Args) != len(s.Fn.Params):
			c.errorf(e.P, "%s expects %d arguments, got %d", e.Name, len(s.Fn.Params), len(e.Args))
		}
	}
}
