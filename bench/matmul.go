package main

import "fmt"

func main() {
	n := 400
	a := make([]int, n*n)
	b := make([]int, n*n)
	c := make([]int, n*n)
	for i := 0; i < n*n; i++ {
		a[i] = i % 7
		b[i] = i % 5
	}
	for i := 0; i < n; i++ {
		for k := 0; k < n; k++ {
			aik := a[i*n+k]
			for j := 0; j < n; j++ {
				c[i*n+j] += aik * b[k*n+j]
			}
		}
	}
	sum := 0
	for i := 0; i < n*n; i++ {
		sum += c[i]
	}
	fmt.Println(sum)
}
