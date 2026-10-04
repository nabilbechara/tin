package main

import (
	"crypto/aes"
	"crypto/cipher"
	"encoding/hex"
	"fmt"
)

// AES-128-GCM over 16 MiB in 16 KiB TLS-sized records.
func main() {
	key := make([]byte, 16)
	for i := range key {
		key[i] = byte(i * 7)
	}
	b, _ := aes.NewCipher(key)
	a, _ := cipher.NewGCM(b)
	data := make([]byte, 16384)
	for i := range data {
		data[i] = byte(i)
	}
	nonce := make([]byte, 12)
	aad := []byte{23, 3, 3, 64, 17}
	var tag []byte
	out := make([]byte, 0, 16384+16)
	for r := 0; r < 1024; r++ {
		nonce[11] = byte(r)
		nonce[10] = byte(r >> 8)
		out = a.Seal(out[:0], nonce, data, aad)
		tag = out[len(out)-16:]
	}
	fmt.Println(hex.EncodeToString(tag))
}
