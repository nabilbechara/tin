package main

import "fmt"

// The Go twin of arena_steps.tin: the same temporaries per step, reclaimed by the GC.
func step(i int64) int64 {
	xs := make([]int64, 0, 16)
	for k := int64(0); k < 100; k++ {
		xs = append(xs, (i+k)&255)
	}
	var t int64
	for _, x := range xs {
		t += x
	}
	return t
}

func main() {
	var total int64
	for i := int64(0); i < 2000000; i++ {
		total += step(i)
	}
	fmt.Println(total)
}
