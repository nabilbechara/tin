package main

import (
	"fmt"
	"strconv"
)

func pi(label string, v int64, err error)   { fmt.Println(label, v, err != nil) }
func pu(label string, v uint64, err error)  { fmt.Println(label, v, err != nil) }
func pf(label string, v float64, err error) { fmt.Println(label, v, err != nil) }
func pb(label string, v bool, err error)    { fmt.Println(label, v, err != nil) }
func ps(label string, v string, err error)  { fmt.Println(label, fmt.Sprintf("%q", v), err != nil) }

func main() {
	fmt.Println("itoa", strconv.Itoa(0), strconv.Itoa(-5), strconv.Itoa(9223372036854775807), strconv.FormatInt(-9223372036854775807-1, 10))
	fmt.Println("formatint", strconv.FormatInt(255, 2), strconv.FormatInt(255, 16), strconv.FormatInt(-255, 16), strconv.FormatInt(123456789, 36))
	fmt.Println("formatuint", strconv.FormatUint(18446744073709551615, 16), strconv.FormatUint(18446744073709551615, 10))
	for _, s := range []string{"123", "-0", "+5", "9223372036854775807", "9223372036854775808", "-9223372036854775808", "abc", "", "12a", " 1"} {
		v, err := strconv.ParseInt(s, 10, 64)
		pi(fmt.Sprintf("atoi %q", s), v, err)
	}
	for _, s := range []string{"0x1f", "-0b101", "0o17", "017", "1_000", "0x_1F", "zz"} {
		v, err := strconv.ParseInt(s, 0, 64)
		pi(fmt.Sprintf("parseint0 %q", s), v, err)
	}
	v36, e36 := strconv.ParseInt("zz", 36, 64)
	pi("parseint36 zz", v36, e36)
	v16, e16 := strconv.ParseInt("-FF", 16, 64)
	pi("parseint16 -FF", v16, e16)
	u1, eu1 := strconv.ParseUint("18446744073709551615", 10, 64)
	pu("parseuint max", u1, eu1)
	u2, eu2 := strconv.ParseUint("18446744073709551616", 10, 64)
	pu("parseuint over", u2, eu2)
	u3, eu3 := strconv.ParseUint("-1", 10, 64)
	pu("parseuint neg", u3, eu3)
	for _, s := range []string{"true", "T", "1", "0", "FALSE", "x", ""} {
		b, err := strconv.ParseBool(s)
		pb(fmt.Sprintf("parsebool %q", s), b, err)
	}
	for _, s := range []string{"3.25", "-0.5", "1e10", "1e400", "-1e400", "0x1p-2", "1e", "", "inf", "+Inf", "1_000.5", ".5", "5."} {
		f, err := strconv.ParseFloat(s, 64)
		pf(fmt.Sprintf("parsefloat %q", s), f, err)
	}
	fmt.Println("formatfloat", strconv.FormatFloat(3.14159, 'f', 2, 64), strconv.FormatFloat(3.14159, 'e', 3, 64), strconv.FormatFloat(3.14159, 'g', -1, 64))
	fmt.Println("formatfloat2", strconv.FormatFloat(1e21, 'g', -1, 64), strconv.FormatFloat(-0.0001234, 'g', 3, 64), strconv.FormatFloat(100, 'f', -1, 64), strconv.FormatFloat(0.1, 'e', -1, 64))
	fmt.Println("quote", strconv.Quote("hi\n\"x\" é\x01\\"), strconv.QuoteRune('☺'), strconv.QuoteRune('\''))
	for _, s := range []string{"\"a\\tb\"", "'x'", "`raw\\n`", "\"bad", "\"\\u00e9\\x41\"", "'ab'", "\"\\q\""} {
		u, err := strconv.Unquote(s)
		ps(fmt.Sprintf("unquote %s", s), u, err)
	}
	b := []byte{}
	b = strconv.AppendInt(b, -42, 10)
	b = strconv.AppendQuote(b, "q")
	fmt.Println("append", string(b))
}
