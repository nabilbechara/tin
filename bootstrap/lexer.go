package main

import (
	"fmt"
	"strconv"
	"strings"
)

// Pos is a source location.
type Pos struct {
	File string
	Line int
	Col  int
}

func (p Pos) String() string { return fmt.Sprintf("%s:%d:%d", p.File, p.Line, p.Col) }

// CompileError is any error reported against the user's source.
type CompileError struct {
	Pos Pos
	Msg string
}

func (e *CompileError) Error() string {
	if e.Pos.File == "" {
		return "error: " + e.Msg
	}
	return fmt.Sprintf("%s: error: %s", e.Pos, e.Msg)
}

// ErrorList collects several compile errors into one error.
type ErrorList []error

func (l ErrorList) Error() string {
	lines := make([]string, len(l))
	for i, e := range l {
		lines[i] = e.Error()
	}
	return strings.Join(lines, "\n")
}

type TokKind int

const (
	TokEOF TokKind = iota
	TokIdent
	TokInt // integer and character literals
	TokString
	TokKeyword
	TokPunct
)

type Token struct {
	Kind TokKind
	Text string // identifier, keyword, punctuation, or decoded string literal
	Val  int64  // value of an integer or character literal
	Pos  Pos
}

var keywords = map[string]bool{
	"fn": true, "extern": true, "const": true, "var": true, "let": true,
	"if": true, "else": true, "while": true, "return": true, "break": true, "continue": true,
}

var twoCharPuncts = map[string]bool{
	"==": true, "!=": true, "<=": true, ">=": true, "<<": true, ">>": true, "&&": true, "||": true,
}

const oneCharPuncts = "(){}[],;=<>+-*/%&|^~!"

type lexer struct {
	file string
	src  []byte
	i    int
	line int
	col  int
}

// Lex turns one source file into tokens, ending with a TokEOF token.
func Lex(file string, src []byte) ([]Token, error) {
	lx := &lexer{file: file, src: src, line: 1, col: 1}
	var toks []Token
	for {
		tok, err := lx.next()
		if err != nil {
			return nil, err
		}
		toks = append(toks, tok)
		if tok.Kind == TokEOF {
			return toks, nil
		}
	}
}

func (lx *lexer) peek(off int) byte {
	if lx.i+off < len(lx.src) {
		return lx.src[lx.i+off]
	}
	return 0
}

func (lx *lexer) advance() byte {
	c := lx.src[lx.i]
	lx.i++
	if c == '\n' {
		lx.line++
		lx.col = 1
	} else {
		lx.col++
	}
	return c
}

func (lx *lexer) errorf(pos Pos, format string, args ...any) error {
	return &CompileError{Pos: pos, Msg: fmt.Sprintf(format, args...)}
}

func (lx *lexer) skipSpaceAndComments() {
	for lx.i < len(lx.src) {
		c := lx.peek(0)
		switch {
		case c == ' ' || c == '\t' || c == '\r' || c == '\n':
			lx.advance()
		case c == '/' && lx.peek(1) == '/':
			for lx.i < len(lx.src) && lx.peek(0) != '\n' {
				lx.advance()
			}
		default:
			return
		}
	}
}

func (lx *lexer) next() (Token, error) {
	lx.skipSpaceAndComments()
	pos := Pos{File: lx.file, Line: lx.line, Col: lx.col}
	if lx.i >= len(lx.src) {
		return Token{Kind: TokEOF, Pos: pos}, nil
	}
	c := lx.peek(0)
	switch {
	case isLetter(c):
		start := lx.i
		for isLetter(lx.peek(0)) || isDigit(lx.peek(0)) {
			lx.advance()
		}
		text := string(lx.src[start:lx.i])
		if keywords[text] {
			return Token{Kind: TokKeyword, Text: text, Pos: pos}, nil
		}
		return Token{Kind: TokIdent, Text: text, Pos: pos}, nil
	case isDigit(c):
		return lx.lexNumber(pos)
	case c == '\'':
		return lx.lexChar(pos)
	case c == '"':
		return lx.lexString(pos)
	}
	if lx.i+1 < len(lx.src) && twoCharPuncts[string(lx.src[lx.i:lx.i+2])] {
		text := string(lx.src[lx.i : lx.i+2])
		lx.advance()
		lx.advance()
		return Token{Kind: TokPunct, Text: text, Pos: pos}, nil
	}
	if strings.IndexByte(oneCharPuncts, c) >= 0 {
		lx.advance()
		return Token{Kind: TokPunct, Text: string(c), Pos: pos}, nil
	}
	return Token{}, lx.errorf(pos, "unexpected character %q", c)
}

func (lx *lexer) lexNumber(pos Pos) (Token, error) {
	start := lx.i
	hex := lx.peek(0) == '0' && (lx.peek(1) == 'x' || lx.peek(1) == 'X')
	if hex {
		lx.advance()
		lx.advance()
		for isHexDigit(lx.peek(0)) {
			lx.advance()
		}
	} else {
		for isDigit(lx.peek(0)) {
			lx.advance()
		}
	}
	for isLetter(lx.peek(0)) || isDigit(lx.peek(0)) {
		lx.advance()
	}
	text := string(lx.src[start:lx.i])
	var val int64
	if hex {
		u, err := strconv.ParseUint(text[2:], 16, 64)
		if err != nil {
			return Token{}, lx.errorf(pos, "invalid number %s", text)
		}
		val = int64(u)
	} else {
		v, err := strconv.ParseInt(text, 10, 64)
		if err != nil {
			return Token{}, lx.errorf(pos, "invalid number %s", text)
		}
		val = v
	}
	return Token{Kind: TokInt, Text: text, Val: val, Pos: pos}, nil
}

func (lx *lexer) lexChar(pos Pos) (Token, error) {
	start := lx.i
	lx.advance()
	if lx.i >= len(lx.src) || lx.peek(0) == '\n' || lx.peek(0) == '\'' {
		return Token{}, lx.errorf(pos, "invalid character literal")
	}
	c := lx.advance()
	if c == '\\' {
		e, err := lx.escape(pos)
		if err != nil {
			return Token{}, err
		}
		c = e
	}
	if lx.peek(0) != '\'' {
		return Token{}, lx.errorf(pos, "unterminated character literal")
	}
	lx.advance()
	return Token{Kind: TokInt, Text: string(lx.src[start:lx.i]), Val: int64(c), Pos: pos}, nil
}

func (lx *lexer) lexString(pos Pos) (Token, error) {
	lx.advance()
	var b []byte
	for {
		if lx.i >= len(lx.src) || lx.peek(0) == '\n' {
			return Token{}, lx.errorf(pos, "unterminated string literal")
		}
		c := lx.advance()
		if c == '"' {
			return Token{Kind: TokString, Text: string(b), Pos: pos}, nil
		}
		if c == '\\' {
			e, err := lx.escape(pos)
			if err != nil {
				return Token{}, err
			}
			c = e
		}
		b = append(b, c)
	}
}

func (lx *lexer) escape(pos Pos) (byte, error) {
	if lx.i >= len(lx.src) {
		return 0, lx.errorf(pos, "unterminated escape sequence")
	}
	c := lx.advance()
	switch c {
	case 'n':
		return '\n', nil
	case 't':
		return '\t', nil
	case 'r':
		return '\r', nil
	case '0':
		return 0, nil
	case '\\', '\'', '"':
		return c, nil
	}
	return 0, lx.errorf(pos, "unknown escape sequence \\%c", c)
}

func isLetter(c byte) bool   { return c == '_' || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') }
func isDigit(c byte) bool    { return c >= '0' && c <= '9' }
func isHexDigit(c byte) bool { return isDigit(c) || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F') }
