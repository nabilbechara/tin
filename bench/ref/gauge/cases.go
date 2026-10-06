package main

// The edge cases of toolchain/tests/v2/gauge_math.tin, run through Go's math package. `go run ./bench/ref/gauge cases`
// prints the lines that test must print (the strict runner sorts them before comparing). Exp, Exp2, Sinh,
// Cosh, Tanh and Pow are Go's pure algorithms from corpus.go: math.Exp is assembly on arm64 and amd64, and
// returns 0 for Exp(-745) where the true value rounds to the smallest subnormal.

import (
	"fmt"
	"math"
	"os"
)

func r(x float64) string { return fmt.Sprintf("%.12g", x) }

func cases() {
	inf, ninf, nan := math.Inf(1), math.Inf(-1), math.NaN()
	nz := math.Copysign(0, -1)
	sub := math.SmallestNonzeroFloat64

	for _, x := range []float64{0, nz, 1, 8, 0.1, -3.75, 1e300, sub, 2.2250738585072014e-308, inf, ninf, nan} {
		f, e := math.Frexp(x)
		i, fr := math.Modf(x)
		fmt.Println("frexp", x, f, e, "modf", i, fr)
	}
	for _, c := range []float64{1, 0.5, -0.75, 1e-310, 3} {
		fmt.Println("ldexp", c, math.Ldexp(c, -1074), math.Ldexp(c, -1075), math.Ldexp(c, -1022), math.Ldexp(c, 1023), math.Ldexp(c, 1024), math.Ldexp(c, 0))
	}
	fmt.Println("ldexp0", math.Ldexp(0, 5), math.Ldexp(nz, 5), math.Ldexp(inf, -5), math.Ldexp(nan, 3))

	for _, p := range [][]float64{{7.5, 2}, {-7.5, 2}, {7.5, -2}, {1e300, 7}, {5, inf}, {inf, 5}, {5, 0}, {0, 3}, {nz, 3}, {1e-310, 3e-311}, {nan, 1}, {17, 5.5}} {
		fmt.Println("mod", p[0], p[1], math.Mod(p[0], p[1]))
	}

	for _, x := range []float64{0, nz, 0.5, 1, -1, 2, 3.141592653589793, 100, 1e6, 536870911, 536870912, 1073741824, 1e10, 1e15, 1e22, 1e100, 1.7e308, inf, nan} {
		fmt.Println("trig", x, r(math.Sin(x)), r(math.Cos(x)), r(math.Tan(x)))
	}
	for _, x := range []float64{0, nz, 0.25, 0.5, 0.6, 0.7, 0.75, 1, -1, 2, -0.5, inf, ninf, nan, 1e-20, 1e300} {
		fmt.Println("inv", x, r(math.Asin(x)), r(math.Acos(x)), r(math.Atan(x)))
	}
	for _, y := range []float64{0, nz, 1, -1, inf, ninf, nan} {
		for _, x := range []float64{0, nz, 1, -1, inf, ninf, nan} {
			fmt.Println("atan2", y, x, r(math.Atan2(y, x)))
		}
	}

	for _, x := range []float64{0, nz, 1, -1, 0.5, 10, 100, 709, 709.78, 710, -708, -745, -745.2, -746, 1e-10, 1e-20, inf, ninf, nan} {
		fmt.Println("exp", x, r(pureExp(x)), r(pureExp2(x)), r(pureSinh(x)), r(pureCosh(x)), r(pureTanh(x)))
	}
	for _, x := range []float64{0, nz, 1, 2, 8, 0.125, 10, 1000, 1e-310, sub, 1e300, 2.5, 0.001, -1, inf, ninf, nan} {
		fmt.Println("log", x, r(math.Log(x)), r(math.Log2(x)), r(math.Log10(x)), r(math.Log1p(x)))
	}
	fmt.Println("log2exact", math.Log2(8), math.Log2(0.125), math.Log2(1), math.Log2(1024), math.Log2(sub))
	fmt.Println("log1p", r(math.Log1p(1e-20)), r(math.Log1p(-0.5)), r(math.Log1p(1e300)), math.Log1p(-1), math.Log1p(-2), math.Log1p(1e-300))

	for _, p := range [][]float64{{2, 0}, {nan, 0}, {1, nan}, {nan, 1}, {-8, 1.0 / 3}, {-2, 3}, {-2, 2}, {0, -1}, {nz, -3}, {nz, 3}, {nz, 2}, {nz, -2},
		{2, 1024}, {2, -1075}, {2, -1074}, {2, 0.5}, {4, -0.5}, {10, 308}, {10, -5}, {10, 2.5}, {-1, inf}, {-1, ninf}, {0.5, inf}, {2, ninf}, {0.5, ninf},
		{inf, -1}, {inf, 2}, {ninf, 3}, {ninf, 2}, {ninf, -3}, {ninf, -2}, {0.1, 3}, {1.0000001, 1e9}, {7, 22}, {123.456, -1.5}, {1e-5, 7.25}, {2, 63}, {2, 64}, {3, 40.5}, {1e300, 2}, {1e-300, 2}} {
		fmt.Println("pow", p[0], p[1], r(purePow(p[0], p[1])))
	}

	for _, x := range []float64{0, nz, 27, -8, 1, 2, 1e-310, sub, 1e300, 0.001, inf, ninf, nan} {
		fmt.Println("cbrt", x, r(math.Cbrt(x)))
	}
	for _, p := range [][]float64{{3, 4}, {-3, 4}, {0, 0}, {inf, nan}, {nan, 5}, {1e300, 1e300}, {sub, sub}, {1e-200, 1e-200}, {5, 12}, {1, 1}} {
		fmt.Println("hypot", p[0], p[1], r(math.Hypot(p[0], p[1])))
	}
}

func init() {
	if len(os.Args) > 1 && os.Args[1] == "cases" {
		cases()
		os.Exit(0)
	}
}
