package main

import (
	"bytes"
	"fmt"
	"strconv"
	"strings"
)

func bs(s string) []byte { return []byte(s) }

func main() {
	a := bs("hello world")
	fmt.Println("equal", bytes.Equal(a, bs("hello world")), bytes.Equal(a, bs("hello")), bytes.Equal(bs(""), bs("")))
	fmt.Println("compare", bytes.Compare(bs("a"), bs("b")), bytes.Compare(bs("b"), bs("a")), bytes.Compare(bs("ab"), bs("a")), bytes.Compare(bs(""), bs("")))
	fmt.Println("indexbyte", bytes.IndexByte(a, 'o'), bytes.IndexByte(a, 'z'), bytes.LastIndexByte(a, 'o'), bytes.IndexByte(bs(""), 'a'))
	fmt.Println("index", bytes.Index(a, bs("world")), bytes.Index(a, bs("wq")), bytes.Index(a, bs("")), bytes.Index(bs("aaab"), bs("aab")), bytes.Contains(a, bs("lo w")))
	fmt.Println("prefix", bytes.HasPrefix(a, bs("hell")), bytes.HasPrefix(a, bs("world")), bytes.HasSuffix(a, bs("world")), bytes.HasSuffix(bs("a"), bs("ab")))
	c := bytes.Clone(a)
	c[0] = 'J'
	fmt.Println("clone", string(a), string(c))
	b := make([]byte, 0, 2)
	b = append(b, "n="...)
	b = strconv.AppendInt(b, -1234, 10)
	b = append(b, ' ')
	b = strconv.AppendUint(b, 18446744073709551615, 10)
	b = append(b, ' ')
	b = strconv.AppendUint(b, 48879, 16)
	fmt.Println("append", string(b), len(b))
	b = b[:2]
	fmt.Println("truncate", string(b))
	b = b[:0]
	fmt.Println("reset", len(b), cap(b) > 0)
	fmt.Println("trim", fmt.Sprintf("%q", string(bytes.TrimSpace(bs("  \t hi there \n")))), fmt.Sprintf("%q", string(bytes.TrimSpace(bs("   ")))))
	fmt.Println("split", strings.Split("a,b,,c", ","), len(strings.Split("", ",")))
	fmt.Println("fields", strings.Fields("  one two\tthree\n "), len(strings.Fields(" ")))
	fmt.Println("case", string(bytes.ToLower(bs("MiXeD 123"))), string(bytes.ToUpper(bs("MiXeD 123"))))
	fmt.Println("repeat", string(bytes.Repeat(bs("ab"), 3)), len(bytes.Repeat(bs("x"), 0)))
}
