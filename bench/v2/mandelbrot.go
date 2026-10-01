package main

import "fmt"

func main() {
	n := 4000
	limit := 4.0
	sum := 0
	for y := 0; y < n; y++ {
		ci := 2.0*float64(y)/float64(n) - 1.0
		byteAcc := 0
		bitNum := 0
		for x := 0; x < n; x++ {
			cr := 2.0*float64(x)/float64(n) - 1.5
			zr, zi, tr, ti := 0.0, 0.0, 0.0, 0.0
			i := 0
			for i < 50 && tr+ti <= limit {
				zi = 2.0*zr*zi + ci
				zr = tr - ti + cr
				tr = zr * zr
				ti = zi * zi
				i++
			}
			byteAcc <<= 1
			if tr+ti <= limit {
				byteAcc |= 1
			}
			bitNum++
			if bitNum == 8 {
				sum += byteAcc * (x + 1)
				byteAcc = 0
				bitNum = 0
			}
		}
	}
	fmt.Println(sum)
}
