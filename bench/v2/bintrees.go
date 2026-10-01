package main

import "fmt"

type Node struct {
	left, right *Node
}

func bottomUp(d int) *Node {
	if d <= 0 {
		return &Node{}
	}
	return &Node{left: bottomUp(d - 1), right: bottomUp(d - 1)}
}

func check(n *Node) int {
	if n.left == nil || n.right == nil {
		return 1
	}
	return 1 + check(n.left) + check(n.right)
}

func main() {
	maxDepth := 18
	stretch := maxDepth + 1
	fmt.Printf("stretch tree of depth %d\t check: %d\n", stretch, check(bottomUp(stretch)))
	longLived := bottomUp(maxDepth)
	total := 0
	for d := 4; d <= maxDepth; d += 2 {
		iters := 1 << (maxDepth - d + 4)
		chk := 0
		for i := 0; i < iters; i++ {
			chk += check(bottomUp(d))
		}
		total += chk
		fmt.Printf("%d\t trees of depth %d\t check: %d\n", iters, d, chk)
	}
	fmt.Printf("long lived tree of depth %d\t check: %d\n", maxDepth, check(longLived))
	fmt.Println(total)
}
