package main

import (
	"crypto/ecdh"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
)

// 200 P-256 ECDH operations, each private key the SHA-256 of a counter.
func main() {
	pk := sha256.Sum256([]byte("peer"))
	peerKey, err := ecdh.P256().NewPrivateKey(pk[:])
	if err != nil {
		fmt.Println(err)
		return
	}
	peer := peerKey.PublicKey()
	acc := sha256.Sum256(nil)
	for i := 0; i < 200; i++ {
		k := sha256.Sum256([]byte(fmt.Sprintf("key %d", i)))
		priv, err := ecdh.P256().NewPrivateKey(k[:])
		if err != nil {
			fmt.Println(err)
			return
		}
		s, _ := priv.ECDH(peer)
		acc = sha256.Sum256(append(acc[:], s...))
	}
	fmt.Println(hex.EncodeToString(acc[:]))
}
