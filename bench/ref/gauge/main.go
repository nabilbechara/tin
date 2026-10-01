package main

import (
	"fmt"
	"math"
	"math/bits"
)

func gcd(a, b int64) int64 {
	if a < 0 {
		a = -a
	}
	if b < 0 {
		b = -b
	}
	for b != 0 {
		a, b = b, a%b
	}
	return a
}

func clamp(x, lo, hi float64) float64 { return math.Max(lo, math.Min(hi, x)) }

func main() {
	fmt.Println("consts", math.Pi, math.E, math.Sqrt2, math.Ln2, int64(math.MaxInt64), int64(math.MinInt64), uint64(math.MaxUint64), math.MaxFloat64, math.SmallestNonzeroFloat64)
	for _, x := range []float64{0, -0.5, 2, 2.5, -2.5, 3.7, -3.7, 1e300, 0.1} {
		fmt.Println("x", x, math.Abs(x), math.Floor(x), math.Ceil(x), math.Trunc(x), math.Round(x), math.RoundToEven(x), math.Signbit(x))
	}
	for _, x := range []float64{0.5, 1, 2, 10, 1e-3, 123.456} {
		fmt.Println("p", x, math.Sqrt(x), math.Cbrt(x), math.Exp(x), math.Exp2(x), math.Log(x), math.Log2(x), math.Log10(x), math.Log1p(x))
		fmt.Println("t", x, math.Sin(x), math.Cos(x), math.Tan(x), math.Atan(x), math.Sinh(x), math.Cosh(x), math.Tanh(x))
	}
	fmt.Println("inv", math.Asin(0.5), math.Acos(0.5), math.Atan2(1, -1), math.Atan2(-1, -1), math.Hypot(3, 4), math.Mod(7.5, 2), math.Mod(-7.5, 2), math.Pow(2, 10), math.Pow(2, 0.5), math.Pow10(3), math.Pow10(-2))
	fmt.Println("minmax", math.Min(1, 2), math.Max(1, 2), math.Min(math.NaN(), 1), math.Max(math.Inf(1), 3), math.Min(math.Copysign(0, -1), 0), min(int64(3), -4), max(int64(3), -4), int64(9), clamp(5, 0, 1), int64(0))
	fmt.Println("special", math.IsNaN(math.NaN()), math.IsInf(math.Inf(-1), -1), math.IsInf(math.Inf(1), 0), math.IsInf(1, 0), math.Copysign(3, -1), math.Inf(1), math.Inf(-1), math.Sqrt(-1))
	fmt.Println("bits", math.Float64bits(1.5), math.Float64frombits(4609434218613702656), math.Float64bits(math.Copysign(0, -1)))
	fmt.Println("int", gcd(48, 18), gcd(-48, 18), gcd(0, 5), int64(12), bits.OnesCount64(255), bits.OnesCount64(math.MaxUint64), bits.LeadingZeros64(1), bits.LeadingZeros64(0), bits.TrailingZeros64(8), bits.TrailingZeros64(0))
}
