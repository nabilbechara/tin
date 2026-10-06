package main

// The Go twin of toolchain/tests/v2/sift_generic.tin: `go run ./bench/ref/sift generic` prints the lines that
// test must print (the strict runner sorts them before comparing). It is Go's slices and cmp, so a
// difference is a difference from Go, including in the order of equal elements after SortFunc.

import (
	"cmp"
	"fmt"
	"math"
	"os"
	"slices"
	"strings"
)

type gItem struct {
	key int64
	id  int64
}

func gGen(shape string, n int, seed int64) []int64 {
	xs := make([]int64, n)
	k := seed
	for i := 0; i < n; i++ {
		k = lcg(k)
		switch shape {
		case "random":
			xs[i] = k
		case "dups":
			xs[i] = (k >> 33) % 10
		case "sorted":
			xs[i] = int64(i)
		case "reversed":
			xs[i] = int64(n - i)
		case "sawtooth":
			xs[i] = int64(i % 17)
		case "equal":
			xs[i] = 7
		default: // organ pipe
			if i < n/2 {
				xs[i] = int64(i)
			} else {
				xs[i] = int64(n - i)
			}
		}
	}
	return xs
}

func gFold(xs []int64) int64 {
	h := int64(0)
	for _, v := range xs {
		h = h*1000003 + v
	}
	return h
}

func gItems(xs []int64) []gItem {
	out := make([]gItem, 0, len(xs))
	for i, k := range xs {
		out = append(out, gItem{key: k, id: int64(i)})
	}
	return out
}

func gIDs(xs []gItem) []int64 {
	out := make([]int64, 0, len(xs))
	for _, it := range xs {
		out = append(out, it.id)
	}
	return out
}

func gByKey(a, b gItem) int     { return cmp.Compare(a.key, b.key) }
func gByKeyDesc(a, b gItem) int { return cmp.Compare(b.key, a.key) }
func gCmpIntStr(a int64, b string) int {
	return cmp.Compare(string(rune(a+48)), b)
}
func gIsEven(x int64) bool        { return x%2 == 0 }
func gEqMod3(a, b int64) bool     { return a%3 == b%3 }
func gEqIntItem(a int64, b gItem) bool { return a == b.key }

func p(args ...any) { fmt.Println(args...) }

func cl(xs []int64) []int64 { return slices.Clone(xs) }

func generic() {
	shapes := []string{"random", "dups", "sorted", "reversed", "sawtooth", "equal", "pipe"}
	sizes := []int{0, 1, 2, 3, 7, 12, 13, 20, 49, 50, 51, 64, 100, 257, 1000, 5000, 20000}
	for _, shape := range shapes {
		for _, n := range sizes {
			xs := gGen(shape, n, int64(n)*31+7)
			a := slices.Clone(xs)
			slices.Sort(a)
			b := gItems(xs)
			slices.SortFunc(b, gByKey)
			c := gItems(xs)
			slices.SortStableFunc(c, gByKey)
			d := gItems(xs)
			slices.SortFunc(d, gByKeyDesc)
			p("sort", shape, n, gFold(a), slices.IsSorted(a), gFold(gIDs(b)), gFold(gIDs(c)), gFold(gIDs(d)), slices.IsSortedFunc(b, gByKey))
		}
	}

	words := make([]string, 0, 40)
	k := int64(5)
	for i := 0; i < 40; i++ {
		k = lcg(k)
		words = append(words, fmt.Sprintf("w%d", (k>>40)%97))
	}
	slices.Sort(words)
	p("strings", words, slices.IsSorted(words))
	nan := math.NaN()
	fs := []float64{3.5, nan, -1, 1e-300, -7.25, 2, 1e300, -1e300, 0.1, 0.2, nan, math.Inf(1), math.Inf(-1)}
	slices.Sort(fs)
	p("floats", fs)
	p("cmp", cmp.Compare(1, 2), cmp.Compare(2, 1), cmp.Compare(3, 3), cmp.Compare(nan, 1.0), cmp.Compare(1.0, nan), cmp.Compare(nan, nan), cmp.Less(nan, 1.0), cmp.Less(1.0, nan), cmp.Less(nan, nan), cmp.Compare("a", "b"))

	sorted := []int64{1, 3, 3, 5, 8, 8, 8, 13, 21}
	for _, t := range []int64{0, 1, 3, 4, 8, 9, 21, 22} {
		i, found := slices.BinarySearch(sorted, t)
		j, found2 := slices.BinarySearchFunc(sorted, string(rune(t+48)), gCmpIntStr)
		p("search", t, i, found, j, found2)
	}
	ie, fe := slices.BinarySearch([]int64{}, 4)
	p("search empty", ie, fe)
	p("minmax", slices.Min(sorted), slices.Max(sorted), slices.Min([]string{"pear", "apple", "fig"}), slices.Max([]string{"pear", "apple", "fig"}), slices.Min([]float64{2.5, -1, 9}), slices.Max([]float64{2.5, -1, 9}))
	p("minmaxfunc", slices.MinFunc(gItems([]int64{5, 2, 9, 2}), gByKey), slices.MaxFunc(gItems([]int64{5, 9, 2, 9}), gByKey))
	p("index", slices.Index(sorted, 8), slices.Index(sorted, 7), slices.Contains(sorted, 13), slices.Contains(sorted, 14), slices.IndexFunc(sorted, gIsEven), slices.ContainsFunc(sorted, gIsEven), slices.Index([]string{"a", "b"}, "b"))

	p("equal", slices.Equal([]int64{1, 2}, []int64{1, 2}), slices.Equal([]int64{1, 2}, []int64{1, 3}), slices.Equal([]int64{1}, []int64{1, 2}), slices.Equal([]string{}, []string{}))
	p("equalfunc", slices.EqualFunc([]int64{1, 4, 7}, []int64{10, 1, 4}, gEqMod3), slices.EqualFunc([]int64{1, 2}, gItems([]int64{1, 2}), gEqIntItem), slices.EqualFunc([]int64{1, 2}, gItems([]int64{1, 3}), gEqIntItem))
	p("compare", slices.Compare([]int64{1, 2, 3}, []int64{1, 2, 4}), slices.Compare([]int64{1, 2, 3}, []int64{1, 2}), slices.Compare([]int64{1, 2}, []int64{1, 2, 3}), slices.Compare([]int64{}, []int64{}), slices.Compare([]float64{nan}, []float64{1}), slices.CompareFunc([]int64{1, 2}, []int64{1, 3}, cmp.Compare[int64]))

	base := []int64{10, 20, 30, 40, 50}
	r := cl(base)
	slices.Reverse(r)
	p("reverse", r, base)
	p("insert", slices.Insert(cl(base), 0, 1), slices.Insert(cl(base), 2, 99), slices.Insert(cl(base), 5, 77))
	p("insertall", slices.Insert(cl(base), 0, []int64{1, 2}...), slices.Insert(cl(base), 3, []int64{7, 8, 9}...), slices.Insert(cl(base), 5, []int64{6}...), slices.Insert(cl(base), 2, []int64{}...))
	p("delete", slices.Delete(cl(base), 0, 2), slices.Delete(cl(base), 1, 4), slices.Delete(cl(base), 4, 5), slices.Delete(cl(base), 2, 2), slices.Delete(cl(base), 0, 5))
	p("deletefunc", slices.DeleteFunc(cl([]int64{1, 2, 3, 4, 5, 6}), gIsEven), slices.DeleteFunc(cl([]int64{1, 3, 5}), gIsEven), slices.DeleteFunc(cl([]int64{2, 4}), gIsEven))
	p("replace", slices.Replace(cl(base), 1, 3, 0), slices.Replace(cl(base), 1, 3, []int64{7, 8, 9, 6}...), slices.Replace(cl(base), 0, 5, []int64{}...), slices.Replace(cl(base), 2, 2, []int64{1, 1}...), slices.Replace(cl(base), 4, 5, []int64{3, 3}...))
	p("compact", slices.Compact(cl([]int64{1, 1, 2, 2, 2, 3, 1, 1})), slices.Compact(cl([]int64{})), slices.Compact(cl([]int64{5})), slices.Compact(cl([]int64{4, 4, 4})), slices.Compact([]string{"a", "a", "b"}))
	p("compactfunc", slices.CompactFunc(cl([]int64{1, 4, 7, 2, 5, 3}), gEqMod3))
	p("clone", slices.Clone(base), len(slices.Clone([]int64{})))
	p("concat", slices.Concat(base, []int64{1}), slices.Concat([]int64{}, base), slices.Concat([]int64{1, 2}, []int64{}, []int64{3}, []int64{4, 5}))
	p("repeat", slices.Repeat([]int64{1, 2}, 3), slices.Repeat([]int64{1, 2}, 0), slices.Repeat([]string{"x"}, 4))
	p("grow", slices.Grow(base, 100), len(slices.Grow(base, 100)))
	_ = strings.ToUpper
}

func init() {
	if len(os.Args) > 1 && os.Args[1] == "generic" {
		generic()
		os.Exit(0)
	}
}
