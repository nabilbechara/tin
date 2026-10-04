package main

import (
	"bytes"
	"fmt"
)

func main() {
	const n = 16
	source, dest := make([]byte, n), make([]byte, n)
	for i := range source {
		source[i] = 7
	}
	source[n-1] = 33
	text := string(source)
	buf := make([]byte, 0, n)
	total := int64(0)
	for i := 0; i < 8388608; i++ {
		buf = buf[:0]
		buf = append(buf, text...)
		copy(dest, buf)
		if !bytes.Equal(source, dest) {
			panic("memory mismatch")
		}
		total += int64(bytes.IndexByte(dest, 33))
	}
	fmt.Println(n, total, dest[n-1])
}
