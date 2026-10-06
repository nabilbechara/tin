// mlkem_twin prints the reference value of toolchain/tests/v2/seal_mlkem.tin with Go's crypto/mlkem (#479):
// for n seeds and messages read from SHAKE128(""), the hash (SHAKE128, 32 bytes) of every
// encapsulation key, ciphertext and shared key, and the implicit-rejection key of a random
// ciphertext. It is the accumulated test of Go's and BoringSSL's ML-KEM suites.
//
// Usage: go run mlkem_twin.go [n]
package main

import (
	"bytes"
	"crypto/mlkem"
	"crypto/mlkem/mlkemtest"
	"crypto/sha3"
	"encoding/hex"
	"fmt"
	"os"
	"strconv"
)

func main() {
	n := 100
	if len(os.Args) > 1 {
		n, _ = strconv.Atoi(os.Args[1])
	}
	s := sha3.NewSHAKE128()
	o := sha3.NewSHAKE128()
	seed := make([]byte, 64)
	msg := make([]byte, 32)
	ct1 := make([]byte, mlkem.CiphertextSize768)
	for i := 0; i < n; i++ {
		s.Read(seed)
		dk, err := mlkem.NewDecapsulationKey768(seed)
		if err != nil {
			panic(err)
		}
		ek := dk.EncapsulationKey()
		o.Write(ek.Bytes())
		s.Read(msg)
		k, ct, err := mlkemtest.Encapsulate768(ek, msg)
		if err != nil {
			panic(err)
		}
		o.Write(ct)
		o.Write(k)
		kk, err := dk.Decapsulate(ct)
		if err != nil || !bytes.Equal(kk, k) {
			panic("decapsulation does not give the key")
		}
		s.Read(ct1)
		k1, err := dk.Decapsulate(ct1)
		if err != nil {
			panic(err)
		}
		o.Write(k1)
	}
	out := make([]byte, 32)
	o.Read(out)
	fmt.Printf("accumulated %d %s\n", n, hex.EncodeToString(out))
}
