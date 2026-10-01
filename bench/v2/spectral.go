package main

import (
	"fmt"
	"math"
)

func a(i, j int) float64 {
	return 1.0 / float64((i+j)*(i+j+1)/2+i+1)
}

func mulAv(v, av []float64) {
	n := len(v)
	for i := 0; i < n; i++ {
		sum := 0.0
		for j := 0; j < n; j++ {
			sum += a(i, j) * v[j]
		}
		av[i] = sum
	}
}

func mulAtv(v, atv []float64) {
	n := len(v)
	for i := 0; i < n; i++ {
		sum := 0.0
		for j := 0; j < n; j++ {
			sum += a(j, i) * v[j]
		}
		atv[i] = sum
	}
}

func mulAtAv(v, out, tmp []float64) {
	mulAv(v, tmp)
	mulAtv(tmp, out)
}

func main() {
	n := 5500
	u := make([]float64, n)
	v := make([]float64, n)
	tmp := make([]float64, n)
	for i := 0; i < n; i++ {
		u[i] = 1.0
	}
	for i := 0; i < 10; i++ {
		mulAtAv(u, v, tmp)
		mulAtAv(v, u, tmp)
	}
	vBv, vv := 0.0, 0.0
	for i := 0; i < n; i++ {
		vBv += u[i] * v[i]
		vv += v[i] * v[i]
	}
	fmt.Printf("%.9f\n", math.Sqrt(vBv/vv))
}
