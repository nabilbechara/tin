// Go reference twin for toolchain/tests/v2/closures.tin
package main

import "fmt"

func makeCounter() func() int64 {
	var n int64
	return func() int64 {
		n++
		return n
	}
}

func adder(base int64) func(int64) int64 {
	return func(x int64) int64 {
		base += x
		return base
	}
}

func each(xs []int64, f func(int64)) {
	for _, x := range xs {
		f(x)
	}
}

func main() {
	xs := []int64{1, 2, 3, 4, 5}
	var total int64
	each(xs, func(x int64) {
		total += x
	})
	fmt.Println("total:", total)
	fmt.Println("pool diff: 0")

	c1 := makeCounter()
	fmt.Println("c1:", c1())
	fmt.Println("c1:", c1())
	fmt.Println("c1:", c1())

	c2 := makeCounter()
	fmt.Println("c2:", c2())
	fmt.Println("c1 again:", c1())

	add10 := adder(10)
	fmt.Println("add10:", add10(5))
	fmt.Println("add10:", add10(3))

	g := makeCounter()
	fmt.Println("global keep:", g())
	fmt.Println("global keep:", g())
}
