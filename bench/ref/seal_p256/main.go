// Go twin of tests/v2/seal_p256.tin.
package main

import (
	"crypto/ecdh"
	"crypto/elliptic"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"math/big"
)

func hx(s string) []byte {
	b, err := hex.DecodeString(s)
	if err != nil {
		panic(err)
	}
	return b
}

func scalar(n *big.Int) []byte {
	return n.FillBytes(make([]byte, 32))
}

func pub(k []byte) string {
	key, err := ecdh.P256().NewPrivateKey(k)
	if err != nil {
		return "fault"
	}
	return hex.EncodeToString(key.PublicKey().Bytes())
}

func shared(k []byte, peer []byte) string {
	key, err := ecdh.P256().NewPrivateKey(k)
	if err != nil {
		return "fault"
	}
	if len(peer) == 33 {
		x, y := elliptic.UnmarshalCompressed(elliptic.P256(), peer)
		if x == nil {
			return "fault"
		}
		peer = elliptic.Marshal(elliptic.P256(), x, y)
	}
	p, err := ecdh.P256().NewPublicKey(peer)
	if err != nil {
		return "fault"
	}
	s, err := key.ECDH(p)
	if err != nil {
		return "fault"
	}
	return hex.EncodeToString(s)
}

func main() {
	n := elliptic.P256().Params().N
	one := big.NewInt(1)
	ks := [][]byte{scalar(one), scalar(big.NewInt(2)), scalar(big.NewInt(15)), scalar(big.NewInt(16)), scalar(big.NewInt(255)),
		scalar(new(big.Int).Sub(n, one)), scalar(new(big.Int).Sub(n, big.NewInt(2))),
		hx("c9afa9d845ba75166b5c215767b1d6934e50c3db36e89b127b8a622b120f6721")}
	for i, k := range ks {
		fmt.Println("pub", i, pub(k))
	}
	bad := [][]byte{make([]byte, 32), scalar(n), scalar(new(big.Int).Add(n, one)), hx("ff"), make([]byte, 33)}
	for i, k := range bad {
		fmt.Println("badpriv", i, pub(k))
	}
	a := hx("0612465c89a023ab17855b0a6bcebfd3febb53aef84138647b5352e02c10c346")
	b := hx("7d7dc5f71eb29ddaf80d6214632eeae03d9058af1fb6d22ed80badb62bc1a534")
	pa := hx(pub(a))
	pb := hx(pub(b))
	fmt.Println("ecdh", shared(a, pb), shared(b, pa))
	// The same point compressed, and with the other y.
	comp := append([]byte{2 + pb[64]&1}, pb[1:33]...)
	flip := append([]byte{3 - pb[64]&1}, pb[1:33]...)
	fmt.Println("compressed", shared(a, comp), shared(a, flip) != shared(a, pb))
	notOn := append([]byte{}, pb...)
	notOn[64] ^= 1
	big1 := append([]byte{4}, make([]byte, 64)...)
	for i := 1; i < 33; i++ {
		big1[i] = 0xff
	}
	peers := [][]byte{notOn, big1, pb[:64], append([]byte{5}, pb[1:]...), {}, {0}, append([]byte{2}, make([]byte, 32)...)}
	for i, p := range peers {
		fmt.Println("badpeer", i, shared(a, p))
	}
	// Fresh keys agree with each other.
	x, _ := ecdh.P256().GenerateKey(rand.Reader)
	y, _ := ecdh.P256().GenerateKey(rand.Reader)
	px := x.PublicKey().Bytes()
	py := y.PublicKey().Bytes()
	fmt.Println("fresh", shared(x.Bytes(), py) == shared(y.Bytes(), px), len(px))
}
