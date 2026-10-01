package main

import "fmt"

func fannkuch(n int) (int, int) {
	perm1 := make([]int, n)
	for i := 0; i < n; i++ {
		perm1[i] = i
	}
	perm := make([]int, n)
	count := make([]int, n)
	maxFlips := 0
	checksum := 0
	r := n
	permCount := 0
	for {
		for r != 1 {
			count[r-1] = r
			r--
		}
		copy(perm, perm1)
		flips := 0
		k := perm[0]
		for k != 0 {
			i := 0
			j := k
			for i < j {
				t := perm[i]
				perm[i] = perm[j]
				perm[j] = t
				i++
				j--
			}
			flips++
			k = perm[0]
		}
		if flips > maxFlips {
			maxFlips = flips
		}
		if permCount%2 == 0 {
			checksum += flips
		} else {
			checksum -= flips
		}
		for {
			if r == n {
				return checksum, maxFlips
			}
			perm0 := perm1[0]
			for i := 0; i < r; i++ {
				perm1[i] = perm1[i+1]
			}
			perm1[r] = perm0
			count[r]--
			if count[r] > 0 {
				break
			}
			r++
		}
		permCount++
	}
}

func main() {
	n := 11
	checksum, maxFlips := fannkuch(n)
	fmt.Printf("%d\nPfannkuchen(%d) = %d\n", checksum, n, maxFlips)
}
