// Go twin of tests/v2/seal_x25519_chacha.tin. Go's standard library has X25519 (crypto/ecdh)
// but no exported ChaCha20-Poly1305, so that part is RFC 8439 written out with math/big.
package main

import (
	"crypto/ecdh"
	"crypto/subtle"
	"encoding/binary"
	"encoding/hex"
	"fmt"
	"math/big"
	"math/bits"
)

func hx(s string) []byte {
	b, err := hex.DecodeString(s)
	if err != nil {
		panic(err)
	}
	return b
}

func x25519(k, u []byte) string {
	if len(k) != 32 || len(u) != 32 {
		return "fault"
	}
	priv, err := ecdh.X25519().NewPrivateKey(k)
	if err != nil {
		return "fault"
	}
	pub, err := ecdh.X25519().NewPublicKey(u)
	if err != nil {
		return "fault"
	}
	s, err := priv.ECDH(pub)
	if err != nil {
		return "fault"
	}
	return hex.EncodeToString(s)
}

func block(key, nonce []byte, ctr uint32) []byte {
	var s [16]uint32
	s[0], s[1], s[2], s[3] = 0x61707865, 0x3320646e, 0x79622d32, 0x6b206574
	for i := 0; i < 8; i++ {
		s[4+i] = binary.LittleEndian.Uint32(key[4*i:])
	}
	s[12] = ctr
	for i := 0; i < 3; i++ {
		s[13+i] = binary.LittleEndian.Uint32(nonce[4*i:])
	}
	x := s
	qr := func(a, b, c, d int) {
		x[a] += x[b]
		x[d] = bits.RotateLeft32(x[d]^x[a], 16)
		x[c] += x[d]
		x[b] = bits.RotateLeft32(x[b]^x[c], 12)
		x[a] += x[b]
		x[d] = bits.RotateLeft32(x[d]^x[a], 8)
		x[c] += x[d]
		x[b] = bits.RotateLeft32(x[b]^x[c], 7)
	}
	for i := 0; i < 10; i++ {
		qr(0, 4, 8, 12)
		qr(1, 5, 9, 13)
		qr(2, 6, 10, 14)
		qr(3, 7, 11, 15)
		qr(0, 5, 10, 15)
		qr(1, 6, 11, 12)
		qr(2, 7, 8, 13)
		qr(3, 4, 9, 14)
	}
	out := make([]byte, 64)
	for i := range x {
		binary.LittleEndian.PutUint32(out[4*i:], x[i]+s[i])
	}
	return out
}

func chacha(key, nonce []byte, ctr uint32, data []byte) []byte {
	out := make([]byte, len(data))
	for off := 0; off < len(data); off += 64 {
		ks := block(key, nonce, ctr)
		for i := off; i < len(data) && i < off+64; i++ {
			out[i] = data[i] ^ ks[i-off]
		}
		ctr++
	}
	return out
}

func le(b []byte) *big.Int {
	r := make([]byte, len(b))
	for i := range b {
		r[len(b)-1-i] = b[i]
	}
	return new(big.Int).SetBytes(r)
}

func poly(key, msg []byte) []byte {
	rb := append([]byte{}, key[:16]...)
	for _, i := range []int{3, 7, 11, 15} {
		rb[i] &= 15
	}
	for _, i := range []int{4, 8, 12} {
		rb[i] &= 252
	}
	r := le(rb)
	p := new(big.Int).Sub(new(big.Int).Lsh(big.NewInt(1), 130), big.NewInt(5))
	acc := new(big.Int)
	for off := 0; off < len(msg); off += 16 {
		end := off + 16
		if end > len(msg) {
			end = len(msg)
		}
		n := le(append(append([]byte{}, msg[off:end]...), 1))
		acc.Add(acc, n).Mul(acc, r).Mod(acc, p)
	}
	acc.Add(acc, le(key[16:]))
	out := make([]byte, 16)
	b := acc.Bytes()
	for i := 0; i < 16 && i < len(b); i++ {
		out[i] = b[len(b)-1-i]
	}
	return out
}

func pad16(b []byte) []byte {
	for len(b)%16 != 0 {
		b = append(b, 0)
	}
	return b
}

func macData(aad, ct []byte) []byte {
	m := pad16(append([]byte{}, aad...))
	m = pad16(append(m, ct...))
	var l [16]byte
	binary.LittleEndian.PutUint64(l[:], uint64(len(aad)))
	binary.LittleEndian.PutUint64(l[8:], uint64(len(ct)))
	return append(m, l[:]...)
}

func sealAEAD(key, nonce, pt, aad []byte) string {
	if len(key) != 32 || len(nonce) != 12 {
		return "fault"
	}
	ct := chacha(key, nonce, 1, pt)
	tag := poly(block(key, nonce, 0)[:32], macData(aad, ct))
	return hex.EncodeToString(append(ct, tag...))
}

func openAEAD(key, nonce, sealed, aad []byte) string {
	if len(key) != 32 || len(nonce) != 12 || len(sealed) < 16 {
		return "fault"
	}
	ct := sealed[:len(sealed)-16]
	tag := poly(block(key, nonce, 0)[:32], macData(aad, ct))
	if subtle.ConstantTimeCompare(tag, sealed[len(ct):]) != 1 {
		return "fault"
	}
	return hex.EncodeToString(chacha(key, nonce, 1, ct))
}

func seq(n, from int) []byte {
	b := make([]byte, n)
	for i := range b {
		b[i] = byte(from + 7*i)
	}
	return b
}

func main() {
	// RFC 7748 section 5.2 and 6.1.
	fmt.Println("x25519", x25519(hx("a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4"), hx("e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c")))
	fmt.Println("x25519", x25519(hx("4b66e9d4d1b4673c5ad22691957d6af5c11b6421e0ea01d42ca4169e7918ba0d"), hx("e5210f12786811d3f4b7959d0538ae2c31dbe7106fc03c3efc4cd549c715a493")))
	a := hx("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a")
	b := hx("5dab087e624a8a4b79e17f8b83800ee66f3bb1292618b6fd1c2f8b27ff88e0eb")
	nine := make([]byte, 32)
	nine[0] = 9
	pa, pb := x25519(a, nine), x25519(b, nine)
	fmt.Println("pub", pa, pb)
	fmt.Println("dh", x25519(a, hx(pb)), x25519(b, hx(pa)))
	k, u := append([]byte{}, nine...), append([]byte{}, nine...)
	for i := 1; i <= 1000; i++ {
		r := hx(x25519(k, u))
		u, k = k, r
		if i == 1 || i == 1000 {
			fmt.Println("iter", i, hex.EncodeToString(k))
		}
	}
	// A low-order point gives an all-zero secret, which must fail; so do wrong lengths.
	fmt.Println("loworder", x25519(a, make([]byte, 32)), x25519(a, hx("e0eb7a7c3b41b8ae1656e3faf19fc46ada098deb9c32b1fd866205165f49b800")))
	fmt.Println("badlen", x25519(a[:31], nine), x25519(a, nine[:31]))
	// RFC 8439 2.4.2 and 2.8.2.
	sun := []byte("Ladies and Gentlemen of the class of '99: If I could offer you only one tip for the future, sunscreen would be it.")
	key := hx("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f")
	fmt.Println("chacha20", hex.EncodeToString(chacha(key, hx("000000000000004a00000000"), 1, sun)))
	akey := hx("808182838485868788898a8b8c8d8e8f909192939495969798999a9b9c9d9e9f")
	nonce := hx("070000004041424344454647")
	aad := hx("50515253c0c1c2c3c4c5c6c7")
	sealed := sealAEAD(akey, nonce, sun, aad)
	fmt.Println("aead", sealed)
	fmt.Println("open", openAEAD(akey, nonce, hx(sealed), aad) == hex.EncodeToString(sun))
	for _, n := range []int{0, 1, 15, 16, 17, 63, 64, 65, 129, 1000} {
		k, no, ad, pt := seq(32, n), seq(12, 3*n), seq(n%20, 5), seq(n, 11)
		s := sealAEAD(k, no, pt, ad)
		sb := hx(s)
		bad := append([]byte{}, sb...)
		bad[len(bad)-1] ^= 0x80
		badct := "fault"
		if n > 0 {
			bc := append([]byte{}, sb...)
			bc[0] ^= 1
			badct = openAEAD(k, no, bc, ad)
		}
		fmt.Println("len", n, s, openAEAD(k, no, sb, ad) == hex.EncodeToString(pt), openAEAD(k, no, bad, ad), badct, openAEAD(k, no, sb, append(ad, 0)), openAEAD(k, seq(12, 1), sb, ad))
	}
	fmt.Println("badkey", sealAEAD(akey[:31], nonce, sun, aad), sealAEAD(akey, nonce[:8], sun, aad), openAEAD(akey, nonce, hx("00"), aad))
}
