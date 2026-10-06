// Reference for toolchain/tests/v2/lever.tin: prints the same lines with Go's flag package.
package main

import (
	"bytes"
	"flag"
	"fmt"
	"io"
	"strings"
)

func e(err error) string {
	if err == nil {
		return "<nil>"
	}
	return err.Error()
}

func dump(tag string, s string) {
	start := 0
	for i := 0; i < len(s); i++ {
		if s[i] == '\n' {
			fmt.Println(tag, fmt.Sprintf("%q", s[start:i]))
			start = i + 1
		}
	}
}

func newSet() *flag.FlagSet {
	fs := flag.NewFlagSet("t", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	return fs
}

func usage(fs *flag.FlagSet) string {
	var b bytes.Buffer
	fs.SetOutput(&b)
	fs.PrintDefaults()
	fs.SetOutput(io.Discard)
	return b.String()
}

func rest(fs *flag.FlagSet) []string {
	r := fs.Args()
	if r == nil {
		return []string{}
	}
	return r
}

func given(fs *flag.FlagSet, name string) bool {
	found := false
	fs.Visit(func(f *flag.Flag) {
		if f.Name == name {
			found = true
		}
	})
	return found
}

func main() {
	// A
	fs := newSet()
	name := fs.String("name", "world", "who to greet")
	n := fs.Int("n", 1, "repeat `count`")
	v := fs.Bool("v", false, "verbose")
	ratio := fs.Float64("ratio", 0.5, "mix ratio")
	fmt.Println("A before", given(fs, "name"), fs.Parsed(), rest(fs), *name, *n, *v, *ratio)
	err := fs.Parse([]string{"-name=tin", "-n", "0x10", "-v", "--ratio", "1e3", "--", "-x", "rest"})
	fmt.Println("A parse", e(err), *name, *n, *v, *ratio, rest(fs), fs.Parsed())
	fmt.Println("A given", given(fs, "name"), given(fs, "n"), given(fs, "v"), given(fs, "ratio"))
	dump("A usage", usage(fs))

	// B
	fs = newSet()
	v = fs.Bool("v", false, "verbose")
	x := fs.Bool("xray", true, "long bool name")
	fmt.Println("B defaults", *v, *x)
	fmt.Println("B false", e(fs.Parse([]string{"-v=false", "-xray=0"})), *v, *x)
	fmt.Println("B true", e(fs.Parse([]string{"-v=1", "--xray", "pos"})), *v, *x, rest(fs))
	bools := []string{"T", "t", "TRUE", "True", "true", "F", "f", "FALSE", "False", "false", "0", "1", "maybe", "tRuE", "", "2", "yes"}
	for _, b := range bools {
		fmt.Println("B value", fmt.Sprintf("%q", b), e(fs.Parse([]string{"-v=" + b})), *v)
	}
	fmt.Println("B next arg", e(fs.Parse([]string{"-v", "false"})), *v, rest(fs))
	dump("B usage", usage(fs))

	// C
	fs = newSet()
	k := fs.Int("k", -5, "an int")
	ints := []string{"010", "0b101", "0o17", "-0x1F", "0X1f", "0B11", "0O7", "1_000", "1__0", "_1", "1_", "0x_f", "0x_", "9223372036854775807", "9223372036854775808", "-9223372036854775808", "-9223372036854775809", "", "+5", "-", "+", "0x", "08", "0", "00", "-0", "0o", "0b2", " 1", "1 ", "1.0", "99999999999999999999x", "0b1111111111111111111111111111111111111111111111111111111111111111", "0x7fffffffffffffff", "0x8000000000000000", "-0x8000000000000000", "0_7", "0x1_f", "+-1", "--1", "1e3", "٣"}
	for _, s := range ints {
		fmt.Println("C value", fmt.Sprintf("%q", s), e(fs.Parse([]string{"-k=" + s})), *k)
	}
	fmt.Println("C next arg", e(fs.Parse([]string{"-k", "-7"})), *k, rest(fs))
	fmt.Println("C twice", e(fs.Parse([]string{"-k", "1", "-k", "2"})), *k)
	fmt.Println("C stops", e(fs.Parse([]string{"-k", "abc", "-k", "9"})), *k)
	dump("C usage", usage(fs))

	// D
	fs = newSet()
	f := fs.Float64("f", 0.25, "a float")
	floats := []string{"1.5", ".5", "5.", "1e-3", "1E3", "inf", "-Infinity", "+inf", "Inf", "nan", "NaN", "-nan", "+nan", "1e400", "-1e400", "1e-400", "0x1p-2", "0x1", "0x1.8p1", "0x.8p1", "0x1P+3", "1_000.5", "1__0.5", "abc", "1e", "1e+", "", "+", "-", ".", "infx", "infinit", "infinityx", "1.2.3", "0x1p", "0xp1", "1e1_0", "-0", "00012", "4.9e-324", "1.7976931348623157e308", "1.7976931348623158e308", "1.7976931348623159e308", "123456789012345678901234567890", "0.1", "1e21", "1e20", "100000000000000000000", "-1.5e-7", "1_e3", "1e_3", " 1", "1 ", "0x", "0x.p1"}
	for _, s := range floats {
		fmt.Println("D value", fmt.Sprintf("%q", s), e(fs.Parse([]string{"-f=" + s})), *f)
	}
	fmt.Println("D next arg", e(fs.Parse([]string{"-f", "-2.5", "tail"})), *f, rest(fs))
	dump("D usage", usage(fs))

	// E
	fs = newSet()
	s := fs.String("s", "", "a string")
	t := fs.String("t", "dflt", "another")
	fmt.Println("E dash value", e(fs.Parse([]string{"-s", "-foo", "-t="})), fmt.Sprintf("%q %q", *s, *t))
	fmt.Println("E empty value", e(fs.Parse([]string{"-s", ""})), fmt.Sprintf("%q", *s))
	fmt.Println("E stops at arg", e(fs.Parse([]string{"a", "-s=x"})), fmt.Sprintf("%q", *s), rest(fs))
	fmt.Println("E lone dash", e(fs.Parse([]string{"-", "-s=x"})), rest(fs))
	fmt.Println("E terminator only", e(fs.Parse([]string{"--"})), rest(fs))
	fmt.Println("E terminator twice", e(fs.Parse([]string{"-s=1", "--", "--", "-t=2"})), fmt.Sprintf("%q %q", *s, *t), rest(fs))
	fmt.Println("E no args", e(fs.Parse([]string{})), rest(fs))
	fmt.Println("E equals in value", e(fs.Parse([]string{"-s=a=b=c"})), *s)
	fmt.Println("E double dash", e(fs.Parse([]string{"--s=dd", "--t", "tt"})), *s, *t)
	fmt.Println("E needs arg", e(fs.Parse([]string{"-s"})))
	fmt.Println("E needs arg after", e(fs.Parse([]string{"-t=ok", "-s"})), *t)
	fmt.Println("E unknown", e(fs.Parse([]string{"-zz"})), e(fs.Parse([]string{"--zz=1"})), e(fs.Parse([]string{"-s=1", "-q", "2"})))
	fmt.Println("E help", e(fs.Parse([]string{"-h"})), e(fs.Parse([]string{"--help"})), e(fs.Parse([]string{"-help"})), e(fs.Parse([]string{"-help=1"})), e(fs.Parse([]string{"-h", "x"})))
	fmt.Println("E syntax", e(fs.Parse([]string{"---x"})), e(fs.Parse([]string{"-=x"})), e(fs.Parse([]string{"--=x"})), e(fs.Parse([]string{"-s=1", "---"})))
	fmt.Println("E repeat", e(fs.Parse([]string{"-t", "x", "-t", "y"})), *t)
	fmt.Println("E unicode", e(fs.Parse([]string{"-s=é", "-t=日本", "ü"})), *s, *t, rest(fs))
	fmt.Println("E set", e(fs.Set("t", "set!")), *t, e(fs.Set("nope", "1")))
	dump("E usage", usage(fs))

	// F
	fs = newSet()
	fs.String("empty", "", "no default shown")
	fs.String("q", "a\"b\\c", "quoted default")
	fs.Int("zero", 0, "int zero")
	fs.Int("neg", -5, "negative\nsecond line")
	fs.Float64("big", 1e21, "huge")
	fs.Float64("two", 2.0, "two")
	fs.Float64("fz", 0, "float zero")
	fs.Float64("small", 0.000001, "tiny")
	fs.Bool("b", true, "bool default true")
	fs.Bool("longbool", false, "a long bool")
	fs.String("nm", "x", "name is `FILE` here")
	fs.Int("i", 3, "`N` items")
	fs.String("odd", "", "one `tick only")
	fs.String("Z", "z", "upper sorts first")
	dump("F usage", usage(fs))
	fmt.Println("F rest before parse", rest(fs), fs.Parsed())
	_ = strings.TrimSpace
}
