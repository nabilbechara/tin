package main

import "fmt"

func main() {
	n := int64(5000000)
	m := make(map[int64]int64)
	k := int64(12345)
	for i := int64(0); i < n; i++ {
		k = k*6364136223846793005 + 1442695040888963407
		m[k] = i
	}
	k = 12345
	sum := int64(0)
	for i := int64(0); i < n; i++ {
		k = k*6364136223846793005 + 1442695040888963407
		sum += m[k]
	}
	miss := int64(0)
	for i := int64(0); i < n; i++ {
		k = k*6364136223846793005 + 1442695040888963407
		_, ok := m[k]
		if !ok {
			miss++
		}
	}
	fmt.Println(len(m), sum, miss)
}
