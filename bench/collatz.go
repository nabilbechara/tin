package main

import "fmt"

func steps(n int) int {
	c := 0
	for n != 1 {
		if n%2 == 0 {
			n = n / 2
		} else {
			n = 3*n + 1
		}
		c++
	}
	return c
}

func main() {
	total := 0
	for i := 1; i < 3000000; i++ {
		total += steps(i)
	}
	fmt.Println(total)
}
