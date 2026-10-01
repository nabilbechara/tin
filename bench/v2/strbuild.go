package main

import "fmt"

func main() {
	strs := []string{"alpha", "be", "gamma!", "d"}
	b := make([]byte, 0)
	for i := 0; i < 10000000; i++ {
		b = append(b, strs[i&3]...)
		b = append(b, byte('0'+i%10))
	}
	sum := 0
	for _, c := range b {
		sum += int(c)
	}
	fmt.Println(len(b), sum)
}
