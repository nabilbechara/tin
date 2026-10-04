package main

import "fmt"

func main() {
	sum := int64(0)
	for i := int64(0); i < 100000000; i++ {
		sum += i / 10
	}
	fmt.Println(sum)
}
