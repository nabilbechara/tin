package main

import "fmt"

func main() {
	n := 20000000
	s := make([]int, n)
	for i := 0; i < n; i++ {
		s[i] = 1
	}
	count := 0
	for i := 2; i < n; i++ {
		if s[i] != 0 {
			count++
			for j := i * i; j < n; j += i {
				s[j] = 0
			}
		}
	}
	fmt.Println(count)
}
