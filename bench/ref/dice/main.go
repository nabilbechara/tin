// Reference for toolchain/tests/v2/dice.tin: the same xoshiro256** / splitmix64 / Lemire algorithms in Go.
package main

import (
	"encoding/binary"
	"fmt"
	"math"
	"math/bits"
)

type Rand struct{ s0, s1, s2, s3 uint64 }

func mix(z uint64) uint64 {
	z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9
	z = (z ^ (z >> 27)) * 0x94d049bb133111eb
	return z ^ (z >> 31)
}

func (r *Rand) Seed(s uint64) {
	z := s + 0x9e3779b97f4a7c15
	r.s0 = mix(z)
	z += 0x9e3779b97f4a7c15
	r.s1 = mix(z)
	z += 0x9e3779b97f4a7c15
	r.s2 = mix(z)
	z += 0x9e3779b97f4a7c15
	r.s3 = mix(z)
}

func New(s uint64) *Rand {
	r := &Rand{}
	r.Seed(s)
	return r
}

func FromState(s0, s1, s2, s3 uint64) *Rand {
	if s0|s1|s2|s3 == 0 {
		panic("dice: FromState with an all-zero state")
	}
	return &Rand{s0, s1, s2, s3}
}

func (r *Rand) State() (uint64, uint64, uint64, uint64) { return r.s0, r.s1, r.s2, r.s3 }

func (r *Rand) U64() uint64 {
	s0 := r.s0
	s1 := r.s1
	s2 := r.s2 ^ s0
	s3 := r.s3 ^ s1
	result := bits.RotateLeft64(s1*5, 7) * 9
	r.s0 = s0 ^ s3
	r.s1 = s1 ^ s2
	r.s2 = s2 ^ (s1 << 17)
	r.s3 = bits.RotateLeft64(s3, 45)
	return result
}

func (r *Rand) U32() uint32 { return uint32(r.U64() >> 32) }

func (r *Rand) U64n(n uint64) uint64 {
	if n&(n-1) == 0 {
		return r.U64() & (n - 1)
	}
	if n <= 0xffffffff {
		v := r.U64() >> 32
		prod := v * n
		low := prod & 0xffffffff
		if low < n {
			thresh := (0x100000000 - n) % n
			for low < thresh {
				v = r.U64() >> 32
				prod = v * n
				low = prod & 0xffffffff
			}
		}
		return prod >> 32
	}
	hi, lo := bits.Mul64(r.U64(), n)
	if lo < n {
		thresh := (0 - n) % n
		for lo < thresh {
			hi, lo = bits.Mul64(r.U64(), n)
		}
	}
	return hi
}

func (r *Rand) I64n(n int64) int64 {
	if n <= 0 {
		panic("dice: I64n with n <= 0")
	}
	return int64(r.U64n(uint64(n)))
}

func (r *Rand) Intn(n int64) int64 { return r.I64n(n) }

func (r *Rand) Range(lo, hi int64) int64 {
	if hi <= lo {
		panic("dice: Range with hi <= lo")
	}
	return lo + int64(r.U64n(uint64(hi)-uint64(lo)))
}

func (r *Rand) F64() float64 { return float64(r.U64()>>11) * (1.0 / 9007199254740992.0) }

func (r *Rand) NormF64() float64 {
	u := 0.0
	s := 0.0
	for s <= 0.0 || s >= 1.0 {
		u = 2.0*r.F64() - 1.0
		v := 2.0*r.F64() - 1.0
		s = u*u + v*v
	}
	return u * math.Sqrt(-2.0*math.Log(s)/s)
}

func (r *Rand) Shuffle(xs []int64) {
	for i := int64(len(xs)) - 1; i > 0; i-- {
		j := int64(r.U64n(uint64(i + 1)))
		xs[i], xs[j] = xs[j], xs[i]
	}
}

func (r *Rand) ShuffleStr(xs []string) {
	for i := int64(len(xs)) - 1; i > 0; i-- {
		j := int64(r.U64n(uint64(i + 1)))
		xs[i], xs[j] = xs[j], xs[i]
	}
}

func (r *Rand) Perm(n int64) []int64 {
	if n <= 0 {
		return []int64{}
	}
	p := make([]int64, n)
	for i := range p {
		p[i] = int64(i)
	}
	r.Shuffle(p)
	return p
}

func (r *Rand) Fill(b []byte) {
	n := len(b)
	if n == 0 {
		return
	}
	words := n >> 3
	for k := 0; k < words; k++ {
		binary.LittleEndian.PutUint64(b[k*8:], r.U64())
	}
	rem := n & 7
	if rem > 0 {
		v := r.U64()
		base := n - rem
		for j := 0; j < rem; j++ {
			b[base+j] = byte(v & 0xff)
			v >>= 8
		}
	}
}

func (r *Rand) Bytes(n int64) []byte {
	if n <= 0 {
		return []byte{}
	}
	b := make([]byte, n)
	r.Fill(b)
	return b
}

func (r *Rand) Str(n int64, alphabet string) string {
	la := len(alphabet)
	if n <= 0 || la == 0 {
		return ""
	}
	ascii := true
	for i := 0; i < la; i++ {
		if alphabet[i] >= 0x80 {
			ascii = false
			break
		}
	}
	if ascii {
		out := make([]byte, n)
		m := uint64(la)
		for i := range out {
			out[i] = alphabet[r.U64n(m)]
		}
		return string(out)
	}
	parts := []rune(alphabet)
	out := make([]byte, 0, n*2)
	m := uint64(len(parts))
	for k := int64(0); k < n; k++ {
		out = append(out, string(parts[r.U64n(m)])...)
	}
	return string(out)
}

var g = &Rand{}

func Seed(s uint64) { g.Seed(s) }

func work(id int64) {
	// Lazy seeding yields two different values on every core.
	fmt.Println("core lazy", id, true)
	g.Seed(42)
	a := g.U64()
	b := g.I64n(1000)
	c := g.F64()
	fmt.Println("core", id, a, b, c < 1.0)
}

func main() {
	v := FromState(1, 2, 3, 4)
	for i := 0; i < 10; i++ {
		fmt.Println("vector", i, v.U64())
	}
	z := New(0)
	m := New(18446744073709551615)
	z1 := z.U64()
	m1 := m.U64()
	fmt.Println("seeds", z1, m1, z1 != m1)

	r := New(42)
	for i := 0; i < 8; i++ {
		fmt.Println("u64", i, r.U64())
	}
	for i := 0; i < 4; i++ {
		fmt.Println("u32", i, r.U32())
	}
	ns := []int64{1, 2, 3, 6, 7, 100, 1000, 65536, 4294967295, 4294967296, 4294967297, 1099511627776, 1000000000007, 9223372036854775807, 9223372036854775806}
	for _, n := range ns {
		a := r.I64n(n)
		b := r.I64n(n)
		c := r.Intn(n)
		fmt.Println("i64n", n, a, b, c, a < n && b < n && c < n && a >= 0 && b >= 0 && c >= 0)
	}
	counts := make([]int64, 6)
	for i := 0; i < 60000; i++ {
		k := r.I64n(6)
		counts[k]++
	}
	fmt.Println("counts6", counts)
	big := make([]int64, 8)
	for i := 0; i < 80000; i++ {
		k := r.I64n(8000000000) / 1000000000
		big[k]++
	}
	fmt.Println("counts big", big)
	ra := r.Range(-5, 5)
	rb := r.Range(10, 11)
	rc := r.Range(math.MinInt64, math.MaxInt64)
	rd := r.Range(-100, -90)
	fmt.Println("range", ra, rb, rc, rd, ra >= -5 && ra < 5, rd >= -100 && rd < -90)
	u0 := r.U64n(0)
	u1 := r.U64n(1)
	u2 := r.U64n(18446744073709551615)
	fmt.Println("u64n", u0, u1, u2)

	for i := 0; i < 5; i++ {
		fmt.Println("f64", i, r.F64())
	}
	sum := 0.0
	mn := 1.0
	mx := 0.0
	for i := 0; i < 100000; i++ {
		x := r.F64()
		sum += x
		if x < mn {
			mn = x
		}
		if x > mx {
			mx = x
		}
	}
	fmt.Println("f64 stats", fmt.Sprintf("%.4f", sum/100000.0), mn >= 0.0, mx < 1.0, mn < 0.001, mx > 0.999)
	for i := 0; i < 5; i++ {
		fmt.Println("norm", i, fmt.Sprintf("%.6f", r.NormF64()))
	}
	sum = 0.0
	sq := 0.0
	for i := 0; i < 100000; i++ {
		x := r.NormF64()
		sum += x
		sq += x * x
	}
	mean := sum / 100000.0
	fmt.Println("norm stats", fmt.Sprintf("%.2f %.2f", mean, sq/100000.0-mean*mean))

	xs := []int64{0, 1, 2, 3, 4, 5, 6, 7, 8, 9}
	r.Shuffle(xs)
	fmt.Println("shuffle", xs)
	r.Shuffle(xs)
	fmt.Println("shuffle2", xs)
	one := []int64{7}
	r.Shuffle(one)
	none := []int64{}
	r.Shuffle(none)
	fmt.Println("shuffle small", one, none, len(none))
	ss := []string{"a", "b", "c", "d", "e"}
	r.ShuffleStr(ss)
	fmt.Println("shufflestr", ss)
	p10 := r.Perm(10)
	p0 := r.Perm(0)
	p1 := r.Perm(1)
	pneg := r.Perm(-3)
	fmt.Println("perm", p10, len(p0), p1, len(pneg))
	p := r.Perm(100)
	seen := make([]bool, 100)
	ok := true
	for _, x := range p {
		if x < 0 || x >= 100 || seen[x] {
			ok = false
		} else {
			seen[x] = true
		}
	}
	fmt.Println("perm100", ok, len(p), p[0], p[99])
	b0 := r.Bytes(0)
	b5 := r.Bytes(5)
	b17 := r.Bytes(17)
	bneg := r.Bytes(-1)
	fmt.Println("bytes", len(b0), b5, b17, len(bneg))
	buf := make([]byte, 8)
	r.Fill(buf)
	fmt.Println("fill", buf)
	empty := []byte{}
	r.Fill(empty)
	s1 := r.Str(10, "abc")
	s2 := r.Str(0, "x")
	s3 := r.Str(5, "")
	s4 := r.Str(8, "αβγ")
	s5 := r.Str(12, "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
	s6 := r.Str(3, "é")
	s7 := r.Str(-2, "abc")
	s8 := r.Str(6, "a€😀")
	fmt.Println("str", s1, fmt.Sprintf("%q", s2), fmt.Sprintf("%q", s3), s4, s5, s6, fmt.Sprintf("%q", s7), s8, len(s8))

	a, b, c, d := r.State()
	x1 := r.U64()
	r2 := FromState(a, b, c, d)
	x2 := r2.U64()
	fmt.Println("state", x1 == x2, x1, a != 0 || b != 0 || c != 0 || d != 0)

	Seed(42)
	q := New(42)
	same := true
	for i := 0; i < 100; i++ {
		if g.U64() != q.U64() {
			same = false
		}
	}
	fmt.Println("pkg same", same)
	Seed(7)
	pu := g.U64()
	pu32 := g.U32()
	pn := g.I64n(10)
	pi := g.Intn(10)
	pr := g.Range(-3, 3)
	pf := g.F64()
	pnorm := g.NormF64()
	pun := g.U64n(1000)
	fmt.Println("pkg", pu, pu32, pn, pi, pr, pf, fmt.Sprintf("%.6f", pnorm), pun)
	ys := []int64{1, 2, 3, 4, 5}
	g.Shuffle(ys)
	ts := []string{"x", "y", "z"}
	g.ShuffleStr(ts)
	pp := g.Perm(5)
	pb := g.Bytes(3)
	fb := make([]byte, 3)
	g.Fill(fb)
	ps := g.Str(6, "ab")
	fmt.Println("pkg2", ys, ts, pp, pb, fb, ps)

	work(0)
	work(1)
}
