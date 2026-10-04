// Go reference for the number parser and the supported float formatting flags.
package main

import (
	"bufio"
	"fmt"
	"math"
	"math/big"
	"math/rand"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

func main() {
	if len(os.Args) != 2 {
		panic("usage: number OUTPUT_DIRECTORY")
	}
	inFile, err := os.Create(filepath.Join(os.Args[1], "input.txt"))
	if err != nil {
		panic(err)
	}
	outFile, err := os.Create(filepath.Join(os.Args[1], "expected.txt"))
	if err != nil {
		panic(err)
	}
	in, out := bufio.NewWriter(inFile), bufio.NewWriter(outFile)
	defer func() {
		if err := in.Flush(); err != nil {
			panic(err)
		}
		if err := out.Flush(); err != nil {
			panic(err)
		}
		inFile.Close()
		outFile.Close()
	}()
	parse := func(s string) {
		fmt.Fprintf(in, "P\t%s\n", s)
		v, err := strconv.ParseFloat(s, 64)
		// Go's capped decimal fallback loses the point for some long integer
		// mantissas. Independently round the exact decimal at 53 bits here.
		if len(s) > 800 && err == nil {
			rat, ok := new(big.Rat).SetString(s)
			if !ok {
				panic("invalid rational: " + s)
			}
			exact := new(big.Float).SetPrec(53).SetMode(big.ToNearestEven).SetRat(rat)
			v, _ = exact.Float64()
		}
		if err != nil {
			fmt.Fprintln(out, "ERR", err)
		} else {
			fmt.Fprintln(out, math.Float64bits(v))
		}
	}
	inputs := []string{"0", "-0", "1", "-1", "0.1", "1.2345678901234567", "1e309", "1e-999", "5e-324", "2.2250738585072014e-308", "2.2250738585072012e-308", "2.2250738585072011e-308", "1.7976931348623157e308", "1.7976931348623158e308", "1.7976931348623159e308", "9007199254740993", "18446744073709551615", "10000000000000000000000000000000000000001e-40", "0x1p-1074", "0x1.fffffffffffffp1023", "0x1.00000000000008p0", "0x1.0000000000000801p0", "Inf", "inf", "INFINITY", "-Inf", "+Inf", "NaN", "nAn", "", " ", " 1", "1 ", "+NaN", "-NaN", "0x1", "1e", "1e+", "1__0", "1_", "_1", "0x_1p0", "0x1_p0", "0x1p_0", ".5", "5.", ".", "0x.p0", "0x1.2.3p0", "1e1_0"}
	for _, s := range inputs {
		parse(s)
	}
	// Exact half-way values with a tail beyond the 800-digit decimal workspace.
	for _, middle := range []string{"1.00000000000000011102230246251565404236316680908203125", "0.999999999999999944488848768742172978818416595458984375"} {
		parse(middle)
		parse(middle + strings.Repeat("0", 1500))
		parse(middle + strings.Repeat("0", 1500) + "1")
	}
	parse("0." + strings.Repeat("0", 2000) + "1e2001")
	parse("1" + strings.Repeat("0", 2000) + "e-2000")
	r := rand.New(rand.NewSource(125))
	values := []float64{0, math.Copysign(0, -1), 0.1, -0.1, 0.125, 0.375, 1.25, 2.5, 9.99999, 999.5, 1e-4, 1e-5, 1e6, 1e20, 1e21, math.SmallestNonzeroFloat64, math.MaxFloat64, math.Float64frombits(0xfffffffffffff), math.Float64frombits(0x10000000000000)}
	for i := 0; i < 20000; i++ {
		v := math.Float64frombits(r.Uint64())
		if math.IsNaN(v) || math.IsInf(v, 0) {
			continue
		}
		parse(strconv.FormatFloat(v, 'g', -1, 64))
		if i < 5000 {
			parse(strconv.FormatFloat(v, 'g', 40, 64))
			parse(strconv.FormatFloat(v, 'x', -1, 64))
		}
		if i < 3000 {
			values = append(values, v)
		}
		fmt.Fprintf(in, "F\t%d\tg\t-1\n", math.Float64bits(v))
		fmt.Fprintln(out, strconv.FormatFloat(v, 'g', -1, 64))
	}
	for _, v := range values {
		for _, verb := range []byte("feEgG") {
			for _, prec := range []int{0, 1, 2, 6, 17, 40, 100} {
				fmt.Fprintf(in, "F\t%d\t%c\t%d\n", math.Float64bits(v), verb, prec)
				fmt.Fprintln(out, strconv.FormatFloat(v, verb, prec, 64))
			}
		}
	}
	formats := []string{"%v", "%g", "%12g", "%012g", "%-12g", "%+g", "%.0f", "%+.2f", "%020.6f", "%-20.6f", "%+020.6e", "%.40E", "%12.0g", "%+.17G"}
	for i := 0; i < 2000; i++ {
		v := math.Float64frombits(r.Uint64())
		if i < len(values) && i < 30 {
			v = values[i]
		}
		if math.IsNaN(v) || math.IsInf(v, 0) {
			continue
		}
		for _, bits := range []int{64, 32} {
			f := v
			if bits == 32 {
				f = float64(float32(v))
			}
			for _, format := range formats {
				fmt.Fprintf(in, "S\t%d\t%s\t%d\n", math.Float64bits(f), format, bits)
				if bits == 32 {
					fmt.Fprintln(out, fmt.Sprintf(format, float32(f)))
				} else {
					fmt.Fprintln(out, fmt.Sprintf(format, f))
				}
			}
		}
	}
	for i := 0; i < 10000; i++ {
		bits := r.Uint32()
		if i < 1000 {
			bits = uint32(i + 1)
		}
		v := math.Float32frombits(bits)
		if math.IsNaN(float64(v)) || math.IsInf(float64(v), 0) {
			continue
		}
		fmt.Fprintf(in, "S\t%d\t%%g\t32\n", math.Float64bits(float64(v)))
		fmt.Fprintln(out, fmt.Sprintf("%g", v))
	}
}
