package main

import (
	"fmt"
	"strings"
	"unicode"
)

func q(s string) string { return fmt.Sprintf("%q", s) }

func qs(xs []string) string {
	out := "["
	for i, x := range xs {
		if i > 0 {
			out += " "
		}
		out += q(x)
	}
	return out + "]"
}

func b(v bool) string { return fmt.Sprint(v) }

func shift(r rune) rune {
	if unicode.IsDigit(r) {
		return -1
	}
	if unicode.IsLetter(r) {
		return r + 1
	}
	return r
}

func isA(r rune) bool {
	return r == 'a' || r == 'A' || r == 0xe9
}

func each(s string) {
	println_("upper", q(s), q(strings.ToUpper(s)))
	println_("lower", q(s), q(strings.ToLower(s)))
	println_("totitle", q(s), q(strings.ToTitle(s)))
	println_("title", q(s), q(strings.Title(s)))
	println_("fields", q(s), qs(strings.Fields(s)))
	println_("fieldsfunc", q(s), qs(strings.FieldsFunc(s, unicode.IsPunct)))
	println_("map", q(s), q(strings.Map(shift, s)))
	println_("trimspace", q(s), q(strings.TrimSpace(s)))
	println_("trimfunc", q(s), q(strings.TrimFunc(s, unicode.IsPunct)))
	println_("trimleftfunc", q(s), q(strings.TrimLeftFunc(s, unicode.IsSpace)))
	println_("trimrightfunc", q(s), q(strings.TrimRightFunc(s, unicode.IsPunct)))
	println_("indexfunc", q(s), strings.IndexFunc(s, unicode.IsUpper))
	println_("lastindexfunc", q(s), strings.LastIndexFunc(s, unicode.IsUpper))
	println_("containsfunc", q(s), b(strings.ContainsFunc(s, isA)))
	println_("explode", q(s), qs(strings.Split(s, "")))
	println_("validutf8", q(s), q(strings.ToValidUTF8(s, "?")))
	println_("validutf8empty", q(s), q(strings.ToValidUTF8(s, "")))
	println_("clone", q(s), q(strings.Clone(s)))
	println_("trimspace2", q(s), q(strings.TrimSpace(strings.ToUpper(s))))
}

func println_(label string, s string, v interface{}) {
	fmt.Println(label, s, v)
}

func lines(s string) {
	var out []string
	for l := range strings.Lines(s) {
		out = append(out, l)
	}
	fmt.Println("lines", q(s), qs(out))
}

func affix(s string, a string) {
	after, ok := strings.CutPrefix(s, a)
	before, ok2 := strings.CutSuffix(s, a)
	fmt.Println("cut", q(s), q(a), q(after), b(ok), q(before), b(ok2))
}

func split(s string, sep string) {
	fmt.Println("splitafter", q(s), q(sep), qs(strings.SplitAfter(s, sep)))
	for _, n := range []int{-1, 0, 1, 2, 3} {
		fmt.Println("splitafterN", q(s), q(sep), n, qs(strings.SplitAfterN(s, sep, n)))
	}
}

func any(s string, chars string) {
	fmt.Println("lastindexany", q(s), q(chars), strings.LastIndexAny(s, chars))
}

func trims(s string, c string) {
	fmt.Println("trim", q(s), q(c), q(strings.Trim(s, c)), q(strings.TrimLeft(s, c)), q(strings.TrimRight(s, c)), strings.IndexAny(s, c), b(strings.ContainsAny(s, c)))
}

func runeat(s string, r rune) {
	fmt.Println("indexrune", q(s), r, strings.IndexRune(s, r), b(strings.ContainsRune(s, r)))
}

func fold(s string, t string) {
	fmt.Println("equalfold", q(s), q(t), b(strings.EqualFold(s, t)), b(strings.EqualFold(t, s)))
}

func replace(pairs []string, s string) {
	r := strings.NewReplacer(pairs...)
	fmt.Println("replace", qs(pairs), q(s), q(r.Replace(s)))
}

func main() {
	texts := []string{"", " ", "a", "Hello, World", "hello world foo_bar baz-qux 9lives", "  leading and trailing  ", "UPPER lower MiXeD 123", "caf\xc3\xa9 \xc3\x89COLE na\xc3\xafve", "stra\xc3\x9fe \xe1\xba\x9e \xc3\x9f", "\xc3\xbf \xc5\xb8 \xc2\xb5 \xce\x9c", "\xc4\xb0stanbul \xc4\xb1 I i", "\xce\xa3\xce\xaf\xcf\x83\xcf\x85\xcf\x86\xce\xbf\xcf\x82 \xcf\x83\xcf\x82", "\xc7\x84 \xc7\x85 \xc7\x86 \xc7\x87 \xc7\x88 \xc7\x89", "\xd0\x9f\xd1\x80\xd0\xb8\xd0\xb2\xd0\xb5\xd1\x82 \xd0\xbc\xd0\xb8\xd1\x80", "\xd9\x85\xd8\xb1\xd8\xad\xd8\xa8\xd8\xa7 \xd8\xa8\xd8\xa7\xd9\x84\xd8\xb9\xd8\xa7\xd9\x84\xd9\x85 123 \xd9\xa1\xd9\xa2\xd9\xa3", "\xe4\xb8\x96\xe7\x95\x8c\xe4\xbd\xa0\xe5\xa5\xbd, \xe3\x81\x93\xe3\x82\x93\xe3\x81\xab\xe3\x81\xa1\xe3\x81\xaf\xe3\x80\x80\xe4\xb8\x96\xe7\x95\x8c", "e\xcc\x81 a\xcc\x88 \xe1\xba\x9b\xcc\xa3", "\xf0\x9f\x98\x80 smile \xf0\x9f\x87\xb8\xf0\x9f\x87\xbe", "\xe2\x84\xaa elvin \xc5\xbf long s", "\xe1\xb2\x80 \xea\x99\x8a \xea\x99\x8b \xe1\x83\x90 \xe1\xb2\x90", "a\xc2\xa0b\xe2\x80\x83c\xe2\x80\xa8d\xe3\x80\x80e\xc2\x85f\xe2\x80\x8bg", "\x09\x0a\x0b\x0c\x0d x \xe2\x80\x89\xe2\x80\x8a", "a\xffb", "\xe4\xb8", "ok\xc0\x80ok\xed\xa0\x80end", "\xf4\x90\x80\x80x", "tr\xc3\xa8s \xc3\xa0 la", "...!!!abc???...", "\xc2\xa1Hola! \xc2\xbfQu\xc3\xa9?", "a,b;c d\x09e", "one\x0atwo\x0d\x0athree\x0a\x0afour", "\x0alead\x0atrail\x0a", "aXbxc", "abcabcabc", "\xc4\x81\xc4\x80\xc4\x83\xc4\x82", "\xe1\xbe\x88 \xe1\xbe\x80 \xe1\xbe\xbc \xe1\xbe\xb3"}
	for _, s := range texts {
		each(s)
		lines(s)
	}
	for _, s := range texts {
		for _, a := range []string{"", "a", "Hello", "lo", "d", "\xc3\xa9", "\x0a", "\xe4\xb8\x96"} {
			affix(s, a)
		}
	}
	for _, s := range texts {
		for _, sep := range []string{"", "a", ",", "\x0a", "\xc3\xa9", "ab", "xyz"} {
			split(s, sep)
		}
	}
	for _, s := range texts {
		for _, c := range []string{"", "aeiou", "\xc3\xa9\xc3\xa8", "\xff", "\xe4\xb8\x96\xe7\x95\x8c", "!.?"} {
			any(s, c)
		}
	}
	for _, s := range texts {
		for _, c := range []string{"", " ", "a", "abc", "\xc3\xa9\xc3\xa8", "\xff", "\xef\xbf\xbd", "\xff\xfe", "\xe4\xb8\x96\xe7\x95\x8c", " .!?,", "\x80"} {
			trims(s, c)
		}
	}
	for _, s := range texts {
		for _, r := range []rune{65, 233, 65533, 19990, 1114112, -1, 55296, 945, 128512, 0} {
			runeat(s, r)
		}
	}
	fold("Go", "GO")
	fold("go", "Go!")
	fold("\xcf\x83", "\xcf\x82")
	fold("\xce\xa3", "\xcf\x82")
	fold("K", "\xe2\x84\xaa")
	fold("k", "\xe2\x84\xaa")
	fold("\xc3\x9f", "\xe1\xba\x9e")
	fold("\xc3\x9f", "SS")
	fold("\xc4\xb0", "i")
	fold("\xc4\xb1", "I")
	fold("\xc7\x84", "\xc7\x86")
	fold("\xc7\x85", "\xc7\x86")
	fold("\xc7\x84", "\xc7\x85")
	fold("", "")
	fold("a", "")
	fold("abc", "ABD")
	fold("\xc3\xa9", "\xc3\x89")
	fold("\xd1\x91", "\xd0\x81")
	fold("\xe1\xb2\x80", "\xd0\xb2")
	fold("a\xffb", "A\xffB")
	fold("\xff", "\xfe")
	fold("\xc3\xa9", "e\xcc\x81")
	fold("\xcd\x85", "\xce\xb9")
	fold("\xe1\xbe\xbe", "\xce\x99")
	replace([]string{"a", "1", "b", "2"}, "abcabc")
	replace([]string{"a", "1", "b", "2"}, "")
	replace([]string{"a", "1", "b", "2"}, "xyz")
	replace([]string{"a", "1", "b", "2"}, "aabb")
	replace([]string{"a", "b", "b", "a"}, "abab")
	replace([]string{"a", "b", "b", "a"}, "aabbcc")
	replace([]string{"ab", "X", "a", "Y", "b", "Z"}, "abab")
	replace([]string{"ab", "X", "a", "Y", "b", "Z"}, "aab")
	replace([]string{"ab", "X", "a", "Y", "b", "Z"}, "bab")
	replace([]string{"a", "X", "ab", "Y"}, "abab")
	replace([]string{"a", "X", "ab", "Y"}, "aab")
	replace([]string{"", "-"}, "abc")
	replace([]string{"", "-"}, "")
	replace([]string{"", "-"}, "\xc3\xa9a")
	replace([]string{"", "-", "a", "A"}, "abc")
	replace([]string{"", "-", "a", "A"}, "aa")
	replace([]string{"a", "A", "", "-"}, "abc")
	replace([]string{"a", "A", "", "-"}, "aa")
	replace([]string{"<", "&lt;", ">", "&gt;", "&", "&amp;"}, "a<b>&c")
	replace([]string{"<", "&lt;", ">", "&gt;", "&", "&amp;"}, "&&<<")
	replace([]string{"\xc3\xa9", "e", "\xc3\xa8", "e"}, "caf\xc3\xa9 \xc3\xa8")
	replace([]string{"\xc3\xa9", "e", "\xc3\xa8", "e"}, "x")
	replace([]string{"hello", "HI", "hell", "X"}, "hello hell help")
	replace([]string{"a", "", "b", ""}, "abcab")
	replace([]string{"aaa", "3", "aa", "2", "a", "1"}, "aaaaaaaa")
	replace([]string{"aaa", "3", "aa", "2", "a", "1"}, "aaaaaaaaaa")
	replace([]string{}, "abc")
	replace([]string{}, "")
}
