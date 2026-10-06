// Go twin of toolchain/tests/v2/seal_aes.tin.
package main

import (
	"crypto/aes"
	"crypto/cipher"
	"encoding/hex"
	"fmt"
)

func hx(s string) []byte {
	b, err := hex.DecodeString(s)
	if err != nil {
		panic(err)
	}
	return b
}

func gcm(key []byte) cipher.AEAD {
	if len(key) != 16 && len(key) != 24 && len(key) != 32 {
		return nil
	}
	b, err := aes.NewCipher(key)
	if err != nil {
		return nil
	}
	g, err := cipher.NewGCM(b)
	if err != nil {
		return nil
	}
	return g
}

func sealGCM(key, nonce, pt, aad []byte) string {
	g := gcm(key)
	if g == nil || len(nonce) != 12 {
		return "fault"
	}
	return hex.EncodeToString(g.Seal(nil, nonce, pt, aad))
}

func openGCM(key, nonce, sealed, aad []byte) string {
	g := gcm(key)
	if g == nil || len(nonce) != 12 {
		return "fault"
	}
	out, err := g.Open(nil, nonce, sealed, aad)
	if err != nil {
		return "fault"
	}
	return hex.EncodeToString(out)
}

func seq(n, from int) []byte {
	b := make([]byte, n)
	for i := range b {
		b[i] = byte(from + 13*i)
	}
	return b
}

func main() {
	// NIST GCM spec test cases 1-4 (AES-128), 7-10 (AES-192) and 13-16 (AES-256).
	pt := hx("d9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a721c3c0c95956809532fcf0e2449a6b525b16aedf5aa0de657ba637b391aafd255")
	aad := hx("feedfacedeadbeeffeedfacedeadbeefabaddad2")
	nonce := hx("cafebabefacedbaddecaf888")
	for _, k := range []string{"feffe9928665731c6d6a8f9467308308", "feffe9928665731c6d6a8f9467308308feffe9928665731c", "feffe9928665731c6d6a8f9467308308feffe9928665731c6d6a8f9467308308"} {
		zero := make([]byte, len(k)/2)
		fmt.Println("nist", len(zero), sealGCM(zero, make([]byte, 12), nil, nil), sealGCM(zero, make([]byte, 12), make([]byte, 16), nil))
		fmt.Println("nist", len(zero), sealGCM(hx(k), nonce, pt, nil))
		fmt.Println("nist", len(zero), sealGCM(hx(k), nonce, pt[:60], aad))
	}
	for _, n := range []int{0, 1, 15, 16, 17, 31, 32, 33, 63, 64, 65, 127, 128, 129, 1000, 16384} {
		for _, kl := range []int{16, 24, 32} {
			k, no, ad, p := seq(kl, n), seq(12, 3*n+kl), seq(n%37, 5), seq(n, 11)
			s := sealGCM(k, no, p, ad)
			sb := hx(s)
			bad := append([]byte{}, sb...)
			bad[len(bad)-1] ^= 0x01
			badct := "fault"
			if n > 0 {
				bc := append([]byte{}, sb...)
				bc[n-1] ^= 0x40
				badct = openGCM(k, no, bc, ad)
			}
			head := s
			if len(head) > 96 {
				head = head[len(head)-96:]
			}
			fmt.Println("len", n, kl, head, openGCM(k, no, sb, ad) == hex.EncodeToString(p), openGCM(k, no, bad, ad), badct, openGCM(k, no, sb, append(ad, 1)), openGCM(k, seq(12, 2), sb, ad))
		}
	}
	fmt.Println("bad", sealGCM(make([]byte, 15), nonce, pt, aad), sealGCM(make([]byte, 33), nonce, pt, aad), sealGCM(make([]byte, 16), nonce[:8], pt, aad), openGCM(make([]byte, 16), nonce, hx("0102"), aad))
}
