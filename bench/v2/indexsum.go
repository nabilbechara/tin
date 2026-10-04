package main

import "fmt"

func main() {
	xs := make([]int64, 1024)
	for i := int64(0); i < int64(len(xs)); i++ {
		xs[i] = i
	}
	n := int64(len(xs))
	total := int64(0)
	for repeat := int64(0); repeat < 100000; repeat++ {
		for i := int64(0); i < n; i++ {
			total += xs[i]
		}
	}
	fmt.Println(total)
}
