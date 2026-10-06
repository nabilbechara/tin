package main

import (
	"crypto/mlkem"
	"crypto/mlkem/mlkemtest"
	"crypto/sha256"
	"crypto/sha512"
	"encoding/hex"
	"fmt"
)

// 200 ML-KEM-768 key generations, encapsulations and decapsulations (#479), the seed and the
// message SHA-512 and SHA-256 of a counter.
func main() {
	acc := sha256.Sum256(nil)
	for i := 0; i < 200; i++ {
		seed := sha512.Sum512([]byte(fmt.Sprintf("seed %d", i)))
		dk, err := mlkem.NewDecapsulationKey768(seed[:])
		if err != nil {
			fmt.Println(err)
			return
		}
		ek := dk.EncapsulationKey()
		m := sha256.Sum256([]byte(fmt.Sprintf("message %d", i)))
		k, ct, err := mlkemtest.Encapsulate768(ek, m[:])
		if err != nil {
			fmt.Println(err)
			return
		}
		k2, err := dk.Decapsulate(ct)
		if err != nil {
			fmt.Println(err)
			return
		}
		buf := append(acc[:], ek.Bytes()...)
		buf = append(buf, ct...)
		buf = append(buf, k...)
		buf = append(buf, k2...)
		acc = sha256.Sum256(buf)
	}
	fmt.Println(hex.EncodeToString(acc[:]))
}
