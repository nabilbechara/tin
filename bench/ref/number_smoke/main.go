package main

import (
	"fmt"
	"math"
	"strconv"
)

func main() {
	for _, s := range []string{"-0", "5e-324", "2.2250738585072012e-308", "2.2250738585072014e-308", "1.7976931348623158e308", "9007199254740993", "0x1.00000000000008p0", "0x1.0000000000000801p0"} {
		x, err := strconv.ParseFloat(s, 64)
		if err != nil {
			panic(err)
		}
		fmt.Println("bits", s, math.Float64bits(x))
	}
	fmt.Println("literals", math.Float64bits(5e-324), math.Float64bits(2.2250738585072012e-308), math.Float64bits(1.00000000000000011102230246251565404236316680908203125))
	for _, x := range []float64{0.125, 0.375, 2.5, -2.5, 9.99999, 1e-100, 1e100} {
		fmt.Println("round", strconv.FormatFloat(x, 'f', 2, 64), strconv.FormatFloat(x, 'e', 0, 64), strconv.FormatFloat(x, 'G', 3, 64))
		fmt.Println("flags", fmt.Sprintf("%+012.2f|%-12.2f|%+.6e", x, x, x))
	}
	fmt.Println("precision", strconv.FormatFloat(0.1, 'f', 40, 64))
	fmt.Println("f32", float32(1.4e-45), float32(1.17549435e-38), float32(3.4028235e38), float32(1)/3)
}
