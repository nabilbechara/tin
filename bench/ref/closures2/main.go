package main

import (
	"cmp"
	"fmt"
	"slices"
	"strings"
	"unicode"
)

type Acc struct {
	n    int64
	name string
}

func loopVars() {
	fs := make([]func() int64, 0, 3)
	for i := int64(0); i < 3; i++ {
		fs = append(fs, func() int64 {
			return i * 10
		})
	}
	for _, f := range fs {
		fmt.Println("loop", f())
	}
	gs := make([]func() int64, 0, 3)
	for _, v := range []int64{7, 8, 9} {
		gs = append(gs, func() int64 {
			return v + 1
		})
	}
	for _, g := range gs {
		fmt.Println("range", g())
	}
}

func deferred() {
	n := 1
	defer func() {
		fmt.Println("deferred sees", n)
	}()
	n = 5
	fmt.Println("body", n)
}

func nested() int64 {
	a := int64(1)
	f := func() func() int64 {
		b := int64(10)
		return func() int64 {
			a++
			b++
			return a*100 + b
		}
	}
	g := f()
	h := f()
	x, y, z := g(), g(), h()
	fmt.Println("nested", x, y, z)
	return a
}

func structs() {
	a := Acc{n: 1, name: "x"}
	inc := func(by int64) {
		a.n += by
	}
	inc(2)
	inc(3)
	fmt.Println("struct", a.n, a.name)
	total := int64(0)
	for _, s := range []Acc{{n: 1, name: "a"}, {n: 2, name: "b"}} {
		show := func() string {
			total += s.n
			return s.name
		}
		fmt.Println("each", show())
	}
	fmt.Println("total", total)
}

func shadow() {
	x := int64(1)
	f := func() int64 {
		x := int64(100)
		x++
		return x
	}
	fmt.Println("shadow", f(), x)
}

var kept func() int64

func keepNested() {
	base := []int64{1, 2, 3}
	kept = func() int64 {
		base = append(base, int64(len(base)))
		return int64(len(base))
	}
}

func library() {
	xs := []int64{5, 2, 8, 1, 9, 3, 7, 4, 6, 0, 15, 12, 11, 14, 13, 10}
	cmps := 0
	slices.SortFunc(xs, func(a, b int64) int {
		cmps++
		return cmp.Compare(a, b)
	})
	fmt.Println("sorted", xs, cmps)
	limit := 3
	seen := 0
	out := strings.Map(func(r rune) rune {
		seen++
		if seen > limit {
			return r - 32
		}
		return r
	}, "abcdefg")
	fmt.Println("map", out, seen)
	sep := rune(0x2c)
	parts := strings.FieldsFunc("a,b;;c,d", func(r rune) bool {
		return r == sep || r == ';'
	})
	fmt.Println("fields", parts)
	_ = unicode.IsSpace
}

func main() {
	loopVars()
	deferred()
	x := nested()
	fmt.Println("outer a", x)
	structs()
	shadow()
	keepNested()
	a, b := kept(), kept()
	fmt.Println("kept", a, b)
	library()
}
