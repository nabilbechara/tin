// Go reference for tests/v2/sift.tin: prints the same lines for the same inputs.
package main

import (
	"cmp"
	"fmt"
	"math"
	"slices"
	"sort"
)

func lcg(k int64) int64 {
	return k*6364136223846793005 + 1442695040888963407
}

func genInts(n int, seed int64) []int64 {
	xs := make([]int64, n)
	k := seed
	for i := 0; i < n; i++ {
		k = lcg(k)
		xs[i] = k
	}
	return xs
}

func genSmall(n int, seed int64, m int64) []int64 {
	xs := make([]int64, n)
	k := seed
	for i := 0; i < n; i++ {
		k = lcg(k)
		xs[i] = (k >> 33) % m
	}
	return xs
}

func checksum(xs []int64) int64 {
	var h int64
	for _, v := range xs {
		h = h*1000003 + v
	}
	return h
}

func oddFirst(a, b int64) bool {
	oa := a & 1
	ob := b & 1
	if oa != ob {
		return oa == 1
	}
	return a < b
}

func desc(a, b int64) bool {
	return a > b
}

func sortBy(xs []int64, less func(a, b int64) bool) {
	slices.SortFunc(xs, func(a, b int64) int {
		if less(a, b) {
			return -1
		}
		if less(b, a) {
			return 1
		}
		return 0
	})
}

func sortDesc(xs []int64) {
	slices.SortFunc(xs, func(a, b int64) int { return cmp.Compare(b, a) })
}

func searchInts(xs []int64, x int64) int {
	return sort.Search(len(xs), func(i int) bool { return xs[i] >= x })
}

func searchStrs(xs []string, x string) int {
	return sort.Search(len(xs), func(i int) bool { return xs[i] >= x })
}

func sumInts(xs []int64) int64 {
	var s int64
	for _, v := range xs {
		s += v
	}
	return s
}

func minInts(xs []int64) (int64, string) {
	if len(xs) == 0 {
		return 0, "sift: MinInts of empty slice"
	}
	return slices.Min(xs), "<nil>"
}

func maxInts(xs []int64) (int64, string) {
	if len(xs) == 0 {
		return 0, "sift: MaxInts of empty slice"
	}
	return slices.Max(xs), "<nil>"
}

func main() {
	e := []int64{}
	slices.Sort(e)
	fmt.Println("ints empty", len(e), slices.IsSorted(e))
	one := []int64{5}
	slices.Sort(one)
	fmt.Println("ints one", one)
	two := []int64{2, 1}
	slices.Sort(two)
	fmt.Println("ints two", two)
	small := []int64{5, 2, 9, 1, 5, 6, -3, 0}
	slices.Sort(small)
	fmt.Println("ints small", small)
	ext := []int64{9223372036854775807, -9223372036854775807 - 1, 0, -1, 1}
	slices.Sort(ext)
	fmt.Println("ints ext", ext)
	r100 := genInts(100, 42)
	slices.Sort(r100)
	fmt.Println("ints 100", slices.IsSorted(r100), r100)
	r1000 := genInts(1000, 7)
	slices.Sort(r1000)
	fmt.Println("ints 1000", slices.IsSorted(r1000), checksum(r1000), r1000[0], r1000[999])
	big := genInts(100000, 99)
	slices.Sort(big)
	fmt.Println("ints 100000", slices.IsSorted(big), checksum(big))
	sorted := make([]int64, 200)
	for i := 0; i < 200; i++ {
		sorted[i] = int64(i) * 3
	}
	slices.Sort(sorted)
	fmt.Println("ints sorted", slices.IsSorted(sorted), checksum(sorted))
	rev := make([]int64, 200)
	for i := 0; i < 200; i++ {
		rev[i] = 1000 - int64(i)
	}
	slices.Sort(rev)
	fmt.Println("ints reversed", slices.IsSorted(rev), rev[0], rev[199], checksum(rev))
	same := make([]int64, 300)
	for i := 0; i < 300; i++ {
		same[i] = 7
	}
	slices.Sort(same)
	fmt.Println("ints same", slices.IsSorted(same), same[0], same[299])
	dup := genSmall(500, 3, 5)
	slices.Sort(dup)
	fmt.Println("ints dups", slices.IsSorted(dup), checksum(dup), dup[0], dup[499])
	saw := make([]int64, 1000)
	for i := 0; i < 1000; i++ {
		saw[i] = int64(i % 37)
	}
	slices.Sort(saw)
	fmt.Println("ints saw", slices.IsSorted(saw), checksum(saw))
	pipe := make([]int64, 1000)
	for i := 0; i < 1000; i++ {
		if i < 500 {
			pipe[i] = int64(i)
		} else {
			pipe[i] = int64(1000 - i)
		}
	}
	slices.Sort(pipe)
	fmt.Println("ints pipe", slices.IsSorted(pipe), checksum(pipe))
	nearly := make([]int64, 300)
	for i := 0; i < 300; i++ {
		nearly[i] = int64(i)
	}
	nearly[10] = 290
	nearly[290] = 10
	nearly[150] = 151
	nearly[151] = 150
	slices.Sort(nearly)
	fmt.Println("ints nearly", slices.IsSorted(nearly), checksum(nearly))

	d1 := []int64{5, 2, 9, 1, 5, 6, -3, 0}
	sortDesc(d1)
	fmt.Println("desc small", d1)
	d2 := []int64{9223372036854775807, -9223372036854775807 - 1, 0, -1, 1}
	sortDesc(d2)
	fmt.Println("desc ext", d2)
	d3 := genInts(100, 42)
	sortDesc(d3)
	fmt.Println("desc 100", d3)
	d4 := []int64{}
	sortDesc(d4)
	fmt.Println("desc empty", len(d4))

	u1 := []uint64{18446744073709551615, 0, 1, 9223372036854775808, 42, 9223372036854775807}
	slices.Sort(u1)
	fmt.Println("u64 small", u1)
	u2 := make([]uint64, 100)
	k := int64(5)
	for i := 0; i < 100; i++ {
		k = lcg(k)
		u2[i] = uint64(k)
	}
	slices.Sort(u2)
	fmt.Println("u64 100", u2)
	u3 := []uint64{}
	slices.Sort(u3)
	fmt.Println("u64 empty", len(u3))

	f1 := []float64{math.NaN(), 3.5, math.Inf(-1), math.Inf(1), math.Copysign(0, -1), 2.25, -1e308, 1e-308, math.NaN(), 0.5, -2.5}
	slices.Sort(f1)
	fmt.Println("f64 small", f1)
	f2 := make([]float64, 100)
	k = 9
	for i := 0; i < 100; i++ {
		k = lcg(k)
		f2[i] = float64(k>>40) / 1024.0
	}
	f2[10] = math.NaN()
	f2[50] = math.NaN()
	slices.Sort(f2)
	fmt.Println("f64 100", f2)
	f3 := []float64{2.5}
	slices.Sort(f3)
	fmt.Println("f64 one", f3)
	f4 := []float64{math.NaN(), math.NaN()}
	slices.Sort(f4)
	fmt.Println("f64 nans", f4)

	s1 := []string{"banana", "apple", "", "Apple", "cherry", "apple", "b", "héllo", "hello", "zz", "a", "aa", "ab"}
	slices.Sort(s1)
	fmt.Println("strs small", slices.IsSorted(s1), s1)
	s2 := make([]string, 100)
	k = 77
	for i := 0; i < 100; i++ {
		k = lcg(k)
		s2[i] = fmt.Sprintf("s%d", (k>>40)%500)
	}
	slices.Sort(s2)
	fmt.Println("strs 100", slices.IsSorted(s2), s2)
	s3 := []string{}
	slices.Sort(s3)
	fmt.Println("strs empty", len(s3))
	s4 := []string{"x"}
	slices.Sort(s4)
	fmt.Println("strs one", s4)

	b1 := genSmall(50, 11, 1000)
	sortBy(b1, oddFirst)
	fmt.Println("sortby odd", b1)
	b2 := []int64{5, 2, 9, 1, 5, 6, -3, 0}
	sortBy(b2, desc)
	fmt.Println("sortby desc", b2)
	b3 := genInts(300, 13)
	sortBy(b3, desc)
	fmt.Println("sortby desc300", checksum(b3), b3[0], b3[299])
	b4 := []int64{}
	sortBy(b4, desc)
	fmt.Println("sortby empty", len(b4))

	st1 := []int64{5, 2, 9, 1, 5, 6, -3, 0}
	slices.SortStableFunc(st1, cmp.Compare)
	fmt.Println("stable small", st1)
	st2 := []int64{9223372036854775807, -9223372036854775807 - 1, 0, -1, 1}
	slices.SortStableFunc(st2, cmp.Compare)
	fmt.Println("stable ext", st2)
	st3 := genInts(1000, 7)
	slices.SortStableFunc(st3, cmp.Compare)
	fmt.Println("stable 1000", slices.IsSorted(st3), checksum(st3))
	st4 := genInts(100000, 99)
	slices.SortStableFunc(st4, cmp.Compare)
	fmt.Println("stable 100000", slices.IsSorted(st4), checksum(st4))
	st5 := make([]int64, 200)
	for i := 0; i < 200; i++ {
		st5[i] = 1000 - int64(i)
	}
	slices.SortStableFunc(st5, cmp.Compare)
	fmt.Println("stable reversed", slices.IsSorted(st5), checksum(st5))
	st6 := genSmall(500, 3, 5)
	slices.SortStableFunc(st6, cmp.Compare)
	fmt.Println("stable dups", slices.IsSorted(st6), checksum(st6))
	st7 := []int64{}
	slices.SortStableFunc(st7, cmp.Compare)
	fmt.Println("stable empty", len(st7))
	st8 := genInts(25, 21)
	slices.SortStableFunc(st8, cmp.Compare)
	fmt.Println("stable 25", st8)

	h1 := []int64{5, 2, 9, 1, 5, 6, -3, 0}
	slices.Sort(h1)
	fmt.Println("heap small", h1)
	h2 := genInts(100, 42)
	slices.Sort(h2)
	fmt.Println("heap 100", slices.IsSorted(h2), checksum(h2))
	h3 := []int64{}
	slices.Sort(h3)
	fmt.Println("heap empty", len(h3))

	fmt.Println("issorted ints", slices.IsSorted([]int64{}), slices.IsSorted([]int64{1}), slices.IsSorted([]int64{1, 2, 2, 3}), slices.IsSorted([]int64{3, 1}), slices.IsSorted([]int64{1, 2, 1}))
	fmt.Println("issorted strs", slices.IsSorted([]string{}), slices.IsSorted([]string{"a", "b"}), slices.IsSorted([]string{"b", "a"}), slices.IsSorted([]string{"a", "a"}), slices.IsSorted([]string{"a", "B"}))

	srch := []int64{1, 3, 3, 5, 8}
	fmt.Println("search ints", searchInts(srch, 0), searchInts(srch, 1), searchInts(srch, 3), searchInts(srch, 4), searchInts(srch, 5), searchInts(srch, 8), searchInts(srch, 9), searchInts([]int64{}, 1))
	srs := []string{"a", "c", "c", "e"}
	fmt.Println("search strs", searchStrs(srs, ""), searchStrs(srs, "a"), searchStrs(srs, "b"), searchStrs(srs, "c"), searchStrs(srs, "d"), searchStrs(srs, "e"), searchStrs(srs, "f"), searchStrs([]string{}, "a"))

	rv1 := []int64{1, 2, 3}
	slices.Reverse(rv1)
	rv2 := []int64{1, 2}
	slices.Reverse(rv2)
	rv3 := []int64{1}
	slices.Reverse(rv3)
	rv4 := []int64{}
	slices.Reverse(rv4)
	fmt.Println("reverse ints", rv1, rv2, rv3, len(rv4))
	rs1 := []string{"a", "b", "c"}
	slices.Reverse(rs1)
	rs2 := []string{}
	slices.Reverse(rs2)
	fmt.Println("reverse strs", rs1, len(rs2))

	q1 := []int64{1, 1, 2, 2, 2, 3}
	n1 := len(slices.Compact(q1))
	fmt.Println("uniq runs", n1, q1[0:n1])
	q2 := []int64{}
	fmt.Println("uniq empty", len(slices.Compact(q2)))
	q3 := []int64{7}
	fmt.Println("uniq one", len(slices.Compact(q3)), q3)
	q4 := []int64{1, 2, 3}
	fmt.Println("uniq distinct", len(slices.Compact(q4)), q4)
	q5 := []int64{5, 5, 5}
	n5 := len(slices.Compact(q5))
	fmt.Println("uniq same", n5, q5[0:n5])
	q6 := genSmall(500, 3, 5)
	slices.Sort(q6)
	n6 := len(slices.Compact(q6))
	fmt.Println("uniq dups", n6, q6[0:n6])

	mn, errMn := minInts([]int64{3, -1, 7})
	mx, errMx := maxInts([]int64{3, -1, 7})
	fmt.Println("minmax", mn, errMn, mx, errMx)
	mn2, errMn2 := minInts([]int64{})
	mx2, errMx2 := maxInts([]int64{})
	fmt.Println("minmax empty", mn2, errMn2, mx2, errMx2)
	mn3, errMn3 := minInts(ext)
	mx3, errMx3 := maxInts(ext)
	fmt.Println("minmax ext", mn3, errMn3, mx3, errMx3)
	mn4, errMn4 := minInts([]int64{4})
	fmt.Println("min one", mn4, errMn4)
	fmt.Println("sum", sumInts([]int64{}), sumInts([]int64{1, 2, 3}), sumInts([]int64{9223372036854775807, 1}), sumInts([]int64{-5}))
	fmt.Println("index", slices.Index([]int64{4, 5, 6}, 5), slices.Index([]int64{4, 5, 6}, 7), slices.Index([]int64{}, 1), slices.Index([]int64{1, 2, 1}, 1), slices.Index([]int64{1, 2, 1}, 2))
	fmt.Println("contains", slices.Contains([]string{"a", "b"}, "b"), slices.Contains([]string{"a", "b"}, "c"), slices.Contains([]string{"a", "b"}, ""), slices.Contains([]string{}, "a"), slices.Contains([]string{"", "x"}, ""), slices.Contains([]string{"héllo"}, "héllo"))
	fmt.Println("equal", slices.Equal([]int64{1, 2}, []int64{1, 2}), slices.Equal([]int64{1, 2}, []int64{1, 2, 3}), slices.Equal([]int64{1, 2}, []int64{1, 3}), slices.Equal([]int64{}, []int64{}), slices.Equal([]int64{}, []int64{0}), slices.Equal(ext, ext))
}
