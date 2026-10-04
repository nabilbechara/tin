package main

import (
	"crypto/sha512"
	"encoding/hex"
	"fmt"
)

// SHA-512 of 64 MiB.
func main() {
	b := make([]byte, 64<<20)
	for i := range b {
		b[i] = byte(i * 31)
	}
	s := sha512.Sum512(b)
	fmt.Println(hex.EncodeToString(s[:]))
}
