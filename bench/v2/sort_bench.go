package main

import (
	"cmp"
	"fmt"
	"slices"
	"time"
)

func checksum(xs []int64) int64 {
	var h int64
	for _, v := range xs {
		h = h*1000003 + v
	}
	return h
}

func main() {
	n := 10000000
	xs := make([]int64, n)
	k := int64(12345)
	for i := 0; i < n; i++ {
		k = k*6364136223846793005 + 1442695040888963407
		xs[i] = k
	}
	ys := make([]int64, n)
	copy(ys, xs)
	fs := make([]float64, n)
	for i := 0; i < n; i++ {
		fs[i] = float64(xs[i]>>20) / 1024.0
	}
	t0 := time.Now()
	slices.Sort(xs)
	t1 := time.Now()
	fmt.Println("ints", slices.IsSorted(xs), checksum(xs), xs[0], xs[n-1])
	t2 := time.Now()
	slices.SortStableFunc(ys, cmp.Compare)
	t3 := time.Now()
	fmt.Println("stable", slices.IsSorted(ys), checksum(ys))
	t4 := time.Now()
	slices.Sort(fs)
	t5 := time.Now()
	fmt.Printf("f64s %.3f %.3f\n", fs[0], fs[n-1])
	t6 := time.Now()
	slices.Sort(xs)
	t7 := time.Now()
	fmt.Println("presorted", slices.IsSorted(xs))
	fmt.Printf("ms ints %d stable %d f64s %d presorted %d\n", t1.Sub(t0).Milliseconds(), t3.Sub(t2).Milliseconds(), t5.Sub(t4).Milliseconds(), t7.Sub(t6).Milliseconds())
}
