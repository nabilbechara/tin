package main

import "fmt"

func main() {
	n := 100000000
	s := make([]byte, n)
	count := 0
	for i := 2; i < n; i++ {
		if s[i] == 0 {
			count++
			for j := i * i; j < n; j += i {
				s[j] = 1
			}
		}
	}
	fmt.Println(count)
}
