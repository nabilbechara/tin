package main

import "fmt"

func main() {
	parts := []string{"cat", "dog", "pig", "fox"}
	b := make([]byte, 0, 3)
	sum := 0
	for i := 0; i < 10000000; i++ {
		b = b[:0]
		b = append(b, parts[i&3]...)
		sum += int(b[0])
	}
	fmt.Println(len(b), sum)
}
