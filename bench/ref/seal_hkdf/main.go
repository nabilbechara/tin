// Go twin of tests/v2/seal_hkdf.tin.
package main

import (
	"crypto/hkdf"
	"crypto/hmac"
	"crypto/sha256"
	"crypto/sha512"
	"encoding/hex"
	"fmt"
	"hash"
	"strings"
)

func hx(s string) []byte {
	b, err := hex.DecodeString(s)
	if err != nil {
		panic(err)
	}
	return b
}

type named struct {
	name string
	h    func() hash.Hash
}

var hashes = []named{{"sha256", sha256.New}, {"sha384", sha512.New384}, {"sha512", sha512.New}}

func sum(h func() hash.Hash, b []byte) []byte {
	x := h()
	x.Write(b)
	return x.Sum(nil)
}

func mac(h func() hash.Hash, key, msg []byte) []byte {
	m := hmac.New(h, key)
	m.Write(msg)
	return m.Sum(nil)
}

func expandLabel(h func() hash.Hash, secret []byte, label string, context []byte, n int) []byte {
	info := []byte{byte(n >> 8), byte(n), byte(6 + len(label))}
	info = append(info, "tls13 "...)
	info = append(info, label...)
	info = append(info, byte(len(context)))
	info = append(info, context...)
	out, err := hkdf.Expand(h, secret, string(info), n)
	if err != nil {
		panic(err)
	}
	return out
}

func main() {
	ins := []string{"", "abc", "abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmnhijklmnoijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu", strings.Repeat("a", 111), strings.Repeat("a", 112), strings.Repeat("a", 127), strings.Repeat("a", 128), strings.Repeat("a", 239), strings.Repeat("a", 240), strings.Repeat("\xff", 1000)}
	for _, s := range ins {
		a := sha512.Sum384([]byte(s))
		b := sha512.Sum512([]byte(s))
		fmt.Println("sha", len(s), hex.EncodeToString(a[:]), hex.EncodeToString(b[:]))
	}
	// RFC 4231 test cases 1, 2, 6 (a 131-byte key) and 7.
	keys := []string{strings.Repeat("0b", 20), hex.EncodeToString([]byte("Jefe")), strings.Repeat("aa", 131), strings.Repeat("aa", 131)}
	msgs := []string{"Hi There", "what do ya want for nothing?", "Test Using Larger Than Block-Size Key - Hash Key First", "This is a test using a larger than block-size key and a larger than block-size data. The key needs to be hashed before being used by the HMAC algorithm."}
	for i := range keys {
		for _, h := range hashes {
			fmt.Println("hmac", i+1, h.name, hex.EncodeToString(mac(h.h, hx(keys[i]), []byte(msgs[i]))))
		}
	}
	// RFC 5869 test cases 1-3, under every hash.
	type tc struct{ ikm, salt, info string; n int }
	long := func(from int) string {
		var b []byte
		for i := 0; i < 80; i++ {
			b = append(b, byte(from+i))
		}
		return hex.EncodeToString(b)
	}
	tcs := []tc{
		{"0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b", "000102030405060708090a0b0c", "f0f1f2f3f4f5f6f7f8f9", 42},
		{long(0), long(0x60), long(0xb0), 82},
		{"0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b", "", "", 42},
	}
	for i, t := range tcs {
		for _, h := range hashes {
			prk, _ := hkdf.Extract(h.h, hx(t.ikm), hx(t.salt))
			okm, _ := hkdf.Expand(h.h, prk, string(hx(t.info)), t.n)
			fmt.Println("hkdf", i+1, h.name, hex.EncodeToString(prk), hex.EncodeToString(okm))
		}
	}
	for _, h := range hashes {
		sz := h.h().Size()
		_, err := hkdf.Expand(h.h, make([]byte, sz), "", 255*sz+1)
		okm, _ := hkdf.Expand(h.h, make([]byte, sz), "", 255*sz)
		fmt.Println("hkdf-limit", h.name, err != nil, len(okm))
	}
	// RFC 8448 section 3: the early secret and its "derived" secret, then the handshake traffic keys.
	zeros := make([]byte, 32)
	early, _ := hkdf.Extract(sha256.New, zeros, zeros)
	empty := sum(sha256.New, nil)
	derived := expandLabel(sha256.New, early, "derived", empty, 32)
	fmt.Println("tls13", hex.EncodeToString(early), hex.EncodeToString(derived))
	shs := hx("b67b7d690cc16c4e75e54213cb2d37b4e9c912bcded9105d42befd59d391ad38")
	fmt.Println("tls13 key", hex.EncodeToString(expandLabel(sha256.New, shs, "key", nil, 16)), hex.EncodeToString(expandLabel(sha256.New, shs, "iv", nil, 12)))
	for _, h := range hashes[1:] {
		fmt.Println("tls13", h.name, hex.EncodeToString(expandLabel(h.h, make([]byte, h.h().Size()), "c hs traffic", []byte("ctx"), h.h().Size())))
	}
}
