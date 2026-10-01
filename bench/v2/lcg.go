package main

import "fmt"

func main() {
	alu := "ACGTacgtNNxxyyzzWWSS"
	buf := make([]byte, 1024)
	seed := 42
	sum := 0
	for i := 0; i < 300000000; i++ {
		seed = (seed*3877 + 29573) % 139968
		c := alu[seed%20]
		buf[i&1023] = c
		sum += int(c) + seed
	}
	fmt.Println(sum, buf[0], buf[1023])
}
