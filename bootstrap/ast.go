package main

// Program is every declaration from every input file.
type Program struct {
	Fns    []*FnDecl
	Consts []*ConstDecl
	Vars   []*VarDecl
}

type FnDecl struct {
	P        Pos
	Name     string
	Params   []string
	Extern   bool
	Body     *Block // nil for extern
	NumSlots int    // params + lets, filled by the checker
}

type ConstDecl struct {
	P    Pos
	Name string
	Init Expr
}

type VarDecl struct {
	P    Pos
	Name string
	Init Expr // nil means zero
	Val  int64
}

// SymKind says what a name refers to.
type SymKind int

const (
	SymLocal SymKind = iota
	SymGlobal
	SymConst
	SymFunc
)

type Symbol struct {
	Kind SymKind
	Name string
	Pos  Pos
	Slot int   // SymLocal: frame slot
	Val  int64 // SymConst: value
	Done bool  // SymConst: value computed
	Fn   *FnDecl
}

type Expr interface{ exprPos() Pos }

type IntLit struct {
	P   Pos
	Val int64
}

type StrLit struct {
	P   Pos
	Val string
}

type Ident struct {
	P    Pos
	Name string
	Ref  *Symbol
}

type Unary struct {
	P  Pos
	Op string // - ! ~ &
	X  Expr
}

type Binary struct {
	P    Pos
	Op   string
	L, R Expr
}

type Call struct {
	P         Pos
	Name      string
	Args      []Expr
	Intrinsic bool
}

// Index is a[i]: the 64-bit word at address a + 8*i.
type Index struct {
	P    Pos
	X, I Expr
}

func (e *IntLit) exprPos() Pos { return e.P }
func (e *StrLit) exprPos() Pos { return e.P }
func (e *Ident) exprPos() Pos  { return e.P }
func (e *Unary) exprPos() Pos  { return e.P }
func (e *Binary) exprPos() Pos { return e.P }
func (e *Call) exprPos() Pos   { return e.P }
func (e *Index) exprPos() Pos  { return e.P }

type Stmt interface{ stmtPos() Pos }

type Block struct {
	P     Pos
	Stmts []Stmt
}

type LetStmt struct {
	P    Pos
	Name string
	Init Expr
	Sym  *Symbol
}

type AssignStmt struct {
	P      Pos
	Target Expr // *Ident or *Index
	Value  Expr
}

type ExprStmt struct {
	P Pos
	X Expr
}

type IfStmt struct {
	P    Pos
	Cond Expr
	Then *Block
	Else Stmt // nil, *Block or *IfStmt
}

type WhileStmt struct {
	P    Pos
	Cond Expr
	Body *Block
}

type ReturnStmt struct {
	P     Pos
	Value Expr // nil means 0
}

type BreakStmt struct{ P Pos }

type ContinueStmt struct{ P Pos }

func (s *Block) stmtPos() Pos        { return s.P }
func (s *LetStmt) stmtPos() Pos      { return s.P }
func (s *AssignStmt) stmtPos() Pos   { return s.P }
func (s *ExprStmt) stmtPos() Pos     { return s.P }
func (s *IfStmt) stmtPos() Pos       { return s.P }
func (s *WhileStmt) stmtPos() Pos    { return s.P }
func (s *ReturnStmt) stmtPos() Pos   { return s.P }
func (s *BreakStmt) stmtPos() Pos    { return s.P }
func (s *ContinueStmt) stmtPos() Pos { return s.P }
