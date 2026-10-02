package main

// The corpus check: every transcendental function over the same deterministic inputs as
// bench/ref/gauge/corpus.tin, printing a hash of the result bits per function (and every result
// with "dump"). Equal hashes mean equal to the last bit. Exp is Go's pure algorithm (copied below),
// because on arm64 and amd64 math.Exp is assembly with a different last bit.

import (
	"fmt"
	"math"
	"os"
)

type rng struct{ s uint64 }

func (r *rng) next() uint64 {
	r.s ^= r.s >> 12
	r.s ^= r.s << 25
	r.s ^= r.s >> 27
	return r.s * 2685821657736338717
}

var edge = []float64{
	0, math.Copysign(0, -1), 1, -1, 0.5, -0.5, 2, -2, 3, 10, 100, 1e-3, 1e-10, 1e-300, 1e300, -1e300,
	math.Inf(1), math.Inf(-1), math.NaN(), math.MaxFloat64, -math.MaxFloat64, math.SmallestNonzeroFloat64,
	-math.SmallestNonzeroFloat64, 2.2250738585072014e-308, 2.225073858507201e-308, 1e-310, 1e-320,
	0.625, 0.66, 0.7, 21, 21.000000000000004, 44.01, 88.03, 709.78, 709.782712893384, 710, -745.13, -745.2,
	1023.9999999999999, 1024, -1074, -1075, 3.725290298461914e-09, 1.862645149230957e-09, 5.551115123125783e-17,
	0.4142135623730951, -0.2928932188134525, 1.4142135623730951, 0.7071067811865476, 0.7853981633974483,
	1.5707963267948966, 3.141592653589793, 6.283185307179586, 536870911, 536870912, 536870913, 1073741824,
	1e10, 1e15, 4503599627370496, 9007199254740992, 9007199254740993, 1e22, 1e100, 1.7e308,
	9.223372036854776e18, 1.8446744073709552e19, 27, -27, 8, 1000, 0.001, 0.1, 0.2, 0.3, 123.456,
}

func inputs() []float64 {
	xs := append([]float64{}, edge...)
	r := &rng{s: 88172645463325252}
	for i := 0; i < 20000; i++ {
		v := r.next()
		m := r.next()
		switch v % 4 {
		case 0:
			xs = append(xs, float64(int(m>>11)%2000001-1000000)/100000)
		case 1:
			e := int(v>>8) % 121
			if e < 0 {
				e = -e
			}
			e -= 60
			bits := uint64(1023+e)<<52 | m&(1<<52-1) | (v>>20&1)<<63
			xs = append(xs, math.Float64frombits(bits))
		case 2:
			xs = append(xs, math.Float64frombits(m))
		default:
			k := int(v>>8)%8001 - 4000
			xs = append(xs, float64(k)/8)
		}
	}
	return xs
}

// Go's exp(), without the assembly fast path.
func pureExp(x float64) float64 {
	const (
		Ln2Hi     = 6.93147180369123816490e-01
		Ln2Lo     = 1.90821492927058770002e-10
		Log2e     = 1.44269504088896338700e+00
		Overflow  = 7.09782712893383973096e+02
		Underflow = -7.45133219101941108420e+02
		NearZero  = 1.0 / (1 << 28)
	)
	switch {
	case math.IsNaN(x):
		return x
	case x > Overflow:
		return math.Inf(1)
	case x < Underflow:
		return 0
	case -NearZero < x && x < NearZero:
		return 1 + x
	}
	var k int
	switch {
	case x < 0:
		k = int(Log2e*x - 0.5)
	case x > 0:
		k = int(Log2e*x + 0.5)
	}
	hi := x - float64(k)*Ln2Hi
	lo := float64(k) * Ln2Lo
	return expmulti(hi, lo, k)
}

func expmulti(hi, lo float64, k int) float64 {
	const (
		P1 = 1.66666666666666657415e-01
		P2 = -2.77777777770155933842e-03
		P3 = 6.61375632143793436117e-05
		P4 = -1.65339022054652515390e-06
		P5 = 4.13813679705723846039e-08
	)
	r := hi - lo
	t := r * r
	c := r - t*(P1+t*(P2+t*(P3+t*(P4+t*P5))))
	y := 1 - ((lo - (r*c)/(2-c)) - hi)
	return math.Ldexp(y, k)
}

func pureExp2(x float64) float64 {
	const (
		Ln2Hi     = 6.93147180369123816490e-01
		Ln2Lo     = 1.90821492927058770002e-10
		Overflow  = 1.0239999999999999e+03
		Underflow = -1.0740e+03
	)
	switch {
	case math.IsNaN(x):
		return x
	case x > Overflow:
		return math.Inf(1)
	case x < Underflow:
		return 0
	}
	var k int
	switch {
	case x > 0:
		k = int(x + 0.5)
	case x < 0:
		k = int(x - 0.5)
	}
	t := x - float64(k)
	hi := t * Ln2Hi
	lo := -t * Ln2Lo
	return expmulti(hi, lo, k)
}

// pureSinh and pureCosh are Go's sinh and cosh over pureExp.
func pureSinh(x float64) float64 {
	const (
		P0 = -0.6307673640497716991184787251e+6
		P1 = -0.8991272022039509355398013511e+5
		P2 = -0.2894211355989563807284660366e+4
		P3 = -0.2630563213397497062819489e+2
		Q0 = -0.6307673640497716991212077277e+6
		Q1 = 0.1521517378790019070696485176e+5
		Q2 = -0.173678953558233699533450911e+3
	)
	sign := false
	if x < 0 {
		x = -x
		sign = true
	}
	var temp float64
	switch {
	case x > 21:
		temp = pureExp(x) * 0.5
	case x > 0.5:
		ex := pureExp(x)
		temp = (ex - 1/ex) * 0.5
	default:
		sq := x * x
		temp = (((P3*sq+P2)*sq+P1)*sq + P0) * x
		temp = temp / (((sq+Q2)*sq+Q1)*sq + Q0)
	}
	if sign {
		temp = -temp
	}
	return temp
}

func pureCosh(x float64) float64 {
	x = math.Abs(x)
	if x > 21 {
		return pureExp(x) * 0.5
	}
	ex := pureExp(x)
	return (ex + 1/ex) * 0.5
}

var tanhP = [...]float64{-9.64399179425052238628e-1, -9.92877231001918586564e1, -1.61468768441708447952e3}
var tanhQ = [...]float64{1.12811678491632931402e2, 2.23548839060100448583e3, 4.84406305325125486048e3}

func pureTanh(x float64) float64 {
	const MAXLOG = 8.8029691931113054295988e+01
	z := math.Abs(x)
	switch {
	case z > 0.5*MAXLOG:
		if x < 0 {
			return -1
		}
		return 1
	case z >= 0.625:
		s := pureExp(2 * z)
		z = 1 - 2/(s+1)
		if x < 0 {
			z = -z
		}
	default:
		if x == 0 {
			return x
		}
		s := x * x
		z = x + x*s*((tanhP[0]*s+tanhP[1])*s+tanhP[2])/(((s+tanhQ[0])*s+tanhQ[1])*s+tanhQ[2])
	}
	return z
}

// pureLog2 and pureLog10 are the same as math's: neither uses Exp.
// pow uses Exp for fractional exponents.
func purePow(x, y float64) float64 {
	// math.Pow calls math.Exp (assembly on arm64/amd64) for the fractional part, so replace that
	// call: copy of math.pow with pureExp.
	isOddInt := func(x float64) bool {
		if math.Abs(x) >= (1 << 53) {
			return false
		}
		xi, xf := math.Modf(x)
		return xf == 0 && int64(xi)&1 == 1
	}
	switch {
	case y == 0 || x == 1:
		return 1
	case y == 1:
		return x
	case math.IsNaN(x) || math.IsNaN(y):
		return math.NaN()
	case x == 0:
		switch {
		case y < 0:
			if math.Signbit(x) && isOddInt(y) {
				return math.Inf(-1)
			}
			return math.Inf(1)
		case y > 0:
			if math.Signbit(x) && isOddInt(y) {
				return x
			}
			return 0
		}
	case math.IsInf(y, 0):
		switch {
		case x == -1:
			return 1
		case (math.Abs(x) < 1) == math.IsInf(y, 1):
			return 0
		default:
			return math.Inf(1)
		}
	case math.IsInf(x, 0):
		if math.IsInf(x, -1) {
			return purePow(1/x, -y)
		}
		switch {
		case y < 0:
			return 0
		case y > 0:
			return math.Inf(1)
		}
	case y == 0.5:
		return math.Sqrt(x)
	case y == -0.5:
		return 1 / math.Sqrt(x)
	}
	yi, yf := math.Modf(math.Abs(y))
	if yf != 0 && x < 0 {
		return math.NaN()
	}
	if yi >= 1<<63 {
		switch {
		case x == -1:
			return 1
		case (math.Abs(x) < 1) == (y > 0):
			return 0
		default:
			return math.Inf(1)
		}
	}
	a1 := 1.0
	ae := 0
	if yf != 0 {
		if yf > 0.5 {
			yf--
			yi++
		}
		a1 = pureExp(yf * math.Log(x))
	}
	x1, xe := math.Frexp(x)
	for i := int64(yi); i != 0; i >>= 1 {
		if xe < -1<<12 || 1<<12 < xe {
			ae += xe
			break
		}
		if i&1 == 1 {
			a1 *= x1
			ae += xe
		}
		x1 *= x1
		xe <<= 1
		if x1 < .5 {
			x1 += x1
			xe--
		}
	}
	if y < 0 {
		a1 = 1 / a1
		ae = -ae
	}
	return math.Ldexp(a1, ae)
}

type unary struct {
	name string
	f    func(float64) float64
}

type binary struct {
	name string
	f    func(float64, float64) float64
}

var unaries = []unary{
	{"sin", math.Sin}, {"cos", math.Cos}, {"tan", math.Tan}, {"asin", math.Asin}, {"acos", math.Acos},
	{"atan", math.Atan}, {"sinh", pureSinh}, {"cosh", pureCosh}, {"tanh", pureTanh}, {"exp", pureExp},
	{"exp2", pureExp2}, {"log", math.Log}, {"log2", math.Log2}, {"log10", math.Log10}, {"log1p", math.Log1p},
	{"cbrt", math.Cbrt},
}

var binaries = []binary{
	{"atan2", math.Atan2}, {"pow", purePow}, {"hypot", math.Hypot}, {"mod", math.Mod},
}

func canon(f float64) uint64 {
	if f != f {
		return 0x7ff8000000000001
	}
	return math.Float64bits(f)
}

type hasher struct{ h uint64 }

func (h *hasher) add(b uint64) {
	for i := 0; i < 8; i++ {
		h.h ^= b >> (8 * uint(i)) & 0xff
		h.h *= 1099511628211
	}
}

func corpus(dump bool) {
	xs := inputs()
	for _, u := range unaries {
		h := hasher{14695981039346656037}
		for i, x := range xs {
			b := canon(u.f(x))
			h.add(b)
			if dump {
				fmt.Printf("%s %d %016x %016x\n", u.name, i, math.Float64bits(x), b)
			}
		}
		if !dump {
			fmt.Printf("%s %d %016x\n", u.name, len(xs), h.h)
		}
	}
	for _, bf := range binaries {
		h := hasher{14695981039346656037}
		n := 0
		for i, x := range xs {
			for _, j := range []int{(i*7 + 3) % len(xs), (i*13 + 1) % len(xs), i} {
				b := canon(bf.f(x, xs[j]))
				h.add(b)
				if dump {
					fmt.Printf("%s %d,%d %016x %016x %016x\n", bf.name, i, j, math.Float64bits(x), math.Float64bits(xs[j]), b)
				}
				n++
			}
		}
		if !dump {
			fmt.Printf("%s %d %016x\n", bf.name, n, h.h)
		}
	}
	// pow with small integer and fractional exponents on positive bases.
	h := hasher{14695981039346656037}
	n := 0
	for _, x := range xs[:2000] {
		for _, y := range []float64{2, 3, -2, 10, -7, 0.25, 1.5, -0.75, 100, 0.3333333333333333, 2.5, -1.5} {
			b := canon(purePow(math.Abs(x), y))
			h.add(b)
			if dump {
				fmt.Printf("powi %d %016x %016x %016x\n", n, math.Float64bits(math.Abs(x)), math.Float64bits(y), b)
			}
			n++
		}
	}
	if !dump {
		fmt.Printf("powi %d %016x\n", n, h.h)
	}
}

func init() {
	if len(os.Args) > 1 && (os.Args[1] == "corpus" || os.Args[1] == "dump") {
		corpus(os.Args[1] == "dump")
		os.Exit(0)
	}
}
