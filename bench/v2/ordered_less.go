package main

import (
	"cmp"
	"fmt"
)

func main() {
	n := 50000000
	hits := 0
	for i := 0; i < n; i++ {
		if cmp.Less(i, n-i) {
			hits++
		}
	}
	fmt.Println(hits)
}
