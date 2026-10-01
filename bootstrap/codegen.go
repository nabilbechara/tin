package main

import (
	"fmt"
	"strings"
)

// The generated code is a stack machine on ARM64: every expression leaves its
// value in x0, binary operators park the left operand on the stack, and locals
// live in 8-byte frame slots below x29. Only x0-x2 and x9 are used as scratch.

const maxFrame = 4095 // largest immediate for `sub sp, sp, #n`

type loopLabels struct{ cont, brk string }

type gen struct {
	out      strings.Builder
	labels   int
	strIdx   map[string]int
	strs     []string
	retLabel string
	loops    []loopLabels
	err      error
}

// Generate emits Mach-O ARM64 assembly for a checked program.
func Generate(prog *Program) (string, error) {
	g := &gen{strIdx: map[string]int{}}
	g.raw("\t.section\t__TEXT,__text,regular,pure_instructions")
	for _, fn := range prog.Fns {
		if !fn.Extern {
			g.genFn(fn)
		}
	}
	if len(prog.Vars) > 0 {
		g.raw("\t.section\t__DATA,__data")
		g.raw("\t.p2align\t3")
		for _, v := range prog.Vars {
			g.raw("_" + v.Name + ":")
			g.emit(".quad %d", v.Val)
		}
	}
	if len(g.strs) > 0 {
		g.raw("\t.section\t__TEXT,__cstring,cstring_literals")
		for i, s := range g.strs {
			g.raw(fmt.Sprintf("l_.str.%d:", i))
			g.emit(".asciz \"%s\"", asmEscape(s))
		}
	}
	return g.out.String(), g.err
}

func (g *gen) raw(line string) {
	g.out.WriteString(line)
	g.out.WriteByte('\n')
}

func (g *gen) emit(format string, args ...any) {
	g.out.WriteByte('\t')
	fmt.Fprintf(&g.out, format, args...)
	g.out.WriteByte('\n')
}

func (g *gen) newLabel() string {
	g.labels++
	return fmt.Sprintf("L%d", g.labels)
}

func (g *gen) label(l string) { g.raw(l + ":") }

func (g *gen) push()          { g.emit("str x0, [sp, #-16]!") }
func (g *gen) pop(reg string) { g.emit("ldr %s, [sp], #16", reg) }

func (g *gen) genFn(fn *FnDecl) {
	frame := (fn.NumSlots*8 + 15) &^ 15
	if frame > maxFrame && g.err == nil {
		g.err = &CompileError{Pos: fn.P, Msg: fmt.Sprintf("function '%s' has too many local variables", fn.Name)}
	}
	g.retLabel = g.newLabel()
	if fn.Name == "main" {
		g.emit(".globl _main")
	}
	g.emit(".p2align 2")
	g.label("_" + fn.Name)
	g.emit("stp x29, x30, [sp, #-16]!")
	g.emit("mov x29, sp")
	if frame > 0 {
		g.emit("sub sp, sp, #%d", frame)
	}
	for i := range fn.Params {
		g.storeSlot(i, fmt.Sprintf("x%d", i))
	}
	g.genStmts(fn.Body.Stmts)
	g.emit("mov x0, #0")
	g.label(g.retLabel)
	g.emit("mov sp, x29")
	g.emit("ldp x29, x30, [sp], #16")
	g.emit("ret")
}

func slotOffset(slot int) int { return 8 * (slot + 1) }

func (g *gen) loadSlot(slot int, reg string) {
	off := slotOffset(slot)
	if off <= 256 {
		g.emit("ldur %s, [x29, #-%d]", reg, off)
		return
	}
	g.emit("sub x9, x29, #%d", off)
	g.emit("ldr %s, [x9]", reg)
}

func (g *gen) storeSlot(slot int, reg string) {
	off := slotOffset(slot)
	if off <= 256 {
		g.emit("stur %s, [x29, #-%d]", reg, off)
		return
	}
	g.emit("sub x9, x29, #%d", off)
	g.emit("str %s, [x9]", reg)
}

func (g *gen) globalAddr(reg, name string) {
	g.emit("adrp %s, _%s@PAGE", reg, name)
	g.emit("add %s, %s, _%s@PAGEOFF", reg, reg, name)
}

func (g *gen) loadImm(reg string, v int64) {
	if v >= -65536 && v <= 65535 {
		g.emit("mov %s, #%d", reg, v)
		return
	}
	u := uint64(v)
	g.emit("movz %s, #%d", reg, u&0xffff)
	for shift := 16; shift < 64; shift += 16 {
		if part := (u >> shift) & 0xffff; part != 0 {
			g.emit("movk %s, #%d, lsl #%d", reg, part, shift)
		}
	}
}

func (g *gen) genStmts(stmts []Stmt) {
	for _, s := range stmts {
		g.genStmt(s)
	}
}

func (g *gen) genStmt(s Stmt) {
	switch s := s.(type) {
	case *Block:
		g.genStmts(s.Stmts)
	case *LetStmt:
		g.genExpr(s.Init)
		g.storeSlot(s.Sym.Slot, "x0")
	case *AssignStmt:
		g.genAssign(s)
	case *ExprStmt:
		g.genExpr(s.X)
	case *IfStmt:
		elseL, endL := g.newLabel(), g.newLabel()
		g.genExpr(s.Cond)
		g.emit("cbz x0, %s", elseL)
		g.genStmts(s.Then.Stmts)
		g.emit("b %s", endL)
		g.label(elseL)
		if s.Else != nil {
			g.genStmt(s.Else)
		}
		g.label(endL)
	case *WhileStmt:
		condL, endL := g.newLabel(), g.newLabel()
		g.label(condL)
		g.genExpr(s.Cond)
		g.emit("cbz x0, %s", endL)
		g.loops = append(g.loops, loopLabels{cont: condL, brk: endL})
		g.genStmts(s.Body.Stmts)
		g.loops = g.loops[:len(g.loops)-1]
		g.emit("b %s", condL)
		g.label(endL)
	case *ReturnStmt:
		if s.Value != nil {
			g.genExpr(s.Value)
		} else {
			g.emit("mov x0, #0")
		}
		g.emit("b %s", g.retLabel)
	case *BreakStmt:
		g.emit("b %s", g.loops[len(g.loops)-1].brk)
	case *ContinueStmt:
		g.emit("b %s", g.loops[len(g.loops)-1].cont)
	}
}

func (g *gen) genAssign(s *AssignStmt) {
	switch t := s.Target.(type) {
	case *Ident:
		g.genExpr(s.Value)
		if t.Ref.Kind == SymLocal {
			g.storeSlot(t.Ref.Slot, "x0")
			return
		}
		g.globalAddr("x9", t.Name)
		g.emit("str x0, [x9]")
	case *Index:
		g.genExpr(t.X)
		g.push()
		g.genExpr(t.I)
		g.push()
		g.genExpr(s.Value)
		g.pop("x1")
		g.pop("x2")
		g.emit("str x0, [x2, x1, lsl #3]")
	}
}

var condCodes = map[string]string{"==": "eq", "!=": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge"}

var arithOps = map[string]string{
	"+": "add", "-": "sub", "*": "mul", "/": "sdiv",
	"&": "and", "|": "orr", "^": "eor", "<<": "lsl", ">>": "asr",
}

func (g *gen) genExpr(e Expr) {
	switch e := e.(type) {
	case *IntLit:
		g.loadImm("x0", e.Val)
	case *StrLit:
		i, ok := g.strIdx[e.Val]
		if !ok {
			i = len(g.strs)
			g.strIdx[e.Val] = i
			g.strs = append(g.strs, e.Val)
		}
		g.emit("adrp x0, l_.str.%d@PAGE", i)
		g.emit("add x0, x0, l_.str.%d@PAGEOFF", i)
	case *Ident:
		switch e.Ref.Kind {
		case SymLocal:
			g.loadSlot(e.Ref.Slot, "x0")
		case SymGlobal:
			g.globalAddr("x9", e.Name)
			g.emit("ldr x0, [x9]")
		case SymConst:
			g.loadImm("x0", e.Ref.Val)
		}
	case *Unary:
		g.genUnary(e)
	case *Binary:
		g.genBinary(e)
	case *Index:
		g.genExpr(e.X)
		g.push()
		g.genExpr(e.I)
		g.emit("mov x1, x0")
		g.pop("x0")
		g.emit("ldr x0, [x0, x1, lsl #3]")
	case *Call:
		g.genCall(e)
	}
}

func (g *gen) genUnary(e *Unary) {
	if e.Op == "&" {
		id := e.X.(*Ident)
		if id.Ref.Kind == SymLocal {
			g.emit("sub x0, x29, #%d", slotOffset(id.Ref.Slot))
		} else {
			g.globalAddr("x0", id.Name)
		}
		return
	}
	g.genExpr(e.X)
	switch e.Op {
	case "-":
		g.emit("neg x0, x0")
	case "~":
		g.emit("mvn x0, x0")
	case "!":
		g.emit("cmp x0, #0")
		g.emit("cset x0, eq")
	}
}

func (g *gen) genBinary(e *Binary) {
	if e.Op == "&&" || e.Op == "||" {
		shortL, endL := g.newLabel(), g.newLabel()
		g.genExpr(e.L)
		if e.Op == "&&" {
			g.emit("cbz x0, %s", shortL)
		} else {
			g.emit("cbnz x0, %s", shortL)
		}
		g.genExpr(e.R)
		g.emit("cmp x0, #0")
		g.emit("cset x0, ne")
		g.emit("b %s", endL)
		g.label(shortL)
		g.emit("mov x0, #%d", b2i(e.Op == "||"))
		g.label(endL)
		return
	}
	g.genExpr(e.L)
	g.push()
	g.genExpr(e.R)
	g.emit("mov x1, x0")
	g.pop("x0")
	if cc, ok := condCodes[e.Op]; ok {
		g.emit("cmp x0, x1")
		g.emit("cset x0, %s", cc)
		return
	}
	if e.Op == "%" {
		g.emit("sdiv x2, x0, x1")
		g.emit("msub x0, x2, x1, x0")
		return
	}
	g.emit("%s x0, x0, x1", arithOps[e.Op])
}

func (g *gen) genCall(e *Call) {
	for _, a := range e.Args {
		g.genExpr(a)
		g.push()
	}
	for i := len(e.Args) - 1; i >= 0; i-- {
		g.pop(fmt.Sprintf("x%d", i))
	}
	if !e.Intrinsic {
		g.emit("bl _%s", e.Name)
		return
	}
	switch e.Name {
	case "load8":
		g.emit("ldrb w0, [x0]")
	case "store8":
		g.emit("strb w1, [x0]")
		g.emit("mov x0, x1")
	}
}

// asmEscape writes bytes the assembler's string syntax can't hold as octal escapes.
func asmEscape(s string) string {
	var b strings.Builder
	for i := 0; i < len(s); i++ {
		c := s[i]
		switch {
		case c == '"' || c == '\\':
			b.WriteByte('\\')
			b.WriteByte(c)
		case c >= 32 && c < 127:
			b.WriteByte(c)
		default:
			fmt.Fprintf(&b, "\\%03o", c)
		}
	}
	return b.String()
}
