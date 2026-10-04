package main

import (
	"crypto/ecdh"
	"encoding/hex"
	"fmt"
)

// 1000 chained X25519 operations (RFC 7748 section 5.2's iteration).
func main() {
	k := make([]byte, 32)
	k[0] = 9
	u := make([]byte, 32)
	u[0] = 9
	for i := 0; i < 1000; i++ {
		priv, _ := ecdh.X25519().NewPrivateKey(k)
		pub, _ := ecdh.X25519().NewPublicKey(u)
		r, err := priv.ECDH(pub)
		if err != nil {
			fmt.Println(err)
			return
		}
		u = k
		k = r
	}
	fmt.Println(hex.EncodeToString(k))
}
