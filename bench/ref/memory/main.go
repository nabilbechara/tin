package main

import (
	"bytes"
	"fmt"
)

func main() {
	for _, n := range []int{0, 1, 2, 7, 8, 9, 15, 16, 17, 47, 48, 49, 63, 64, 65, 95, 96, 97, 127, 128, 129, 255, 256, 257, 1023, 1024, 1025, 4095, 4096, 4097, 1048576} {
		sum := 0
		for a := 0; a < 8; a++ {
			for b := 0; b < 8; b++ {
				source, dest := make([]byte, n+32), make([]byte, n+32)
				p, q := source[a:a+n], dest[b:b+n]
				for i := range p {
					p[i] = byte(i*13 + 7)
				}
				for i := range q {
					q[i] = 165
				}
				copy(q, p)
				if !bytes.Equal(p, q) {
					panic("copy")
				}
				for c := 0; c < 256; c += 17 {
					if found := bytes.IndexByte(p, byte(c)); found >= 0 {
						sum += found + 1
					}
				}
				for i := 0; i < 16; i++ {
					source[i] = byte(i + 1)
				}
				copy(source[3:16], source[:13])
				copy(source[:13], source[3:16])
				for i := 0; i < 13; i++ {
					if source[i] != byte(i+1) {
						panic("overlap")
					}
				}
			}
		}
		fmt.Println("memory", n, sum)
	}
	fmt.Println("allocator zero aligned realloc guard")
	fmt.Println("cross-core return")
}
