package main

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/ecdh"
	"crypto/hkdf"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
)

func label(secret []byte, l string, ctx []byte, n int) []byte {
	info := []byte{byte(n >> 8), byte(n), byte(6 + len(l))}
	info = append(info, "tls13 "...)
	info = append(info, l...)
	info = append(info, byte(len(ctx)))
	info = append(info, ctx...)
	out, _ := hkdf.Expand(sha256.New, secret, string(info), n)
	return out
}

func mac(key, msg []byte) []byte {
	m := hmac.New(sha256.New, key)
	m.Write(msg)
	return m.Sum(nil)
}

// The client's cryptography for 300 TLS 1.3 handshakes: an X25519 key share and shared
// secret, the key schedule, four AES-128-GCM keys and both Finished MACs.
func main() {
	sk := sha256.Sum256([]byte("server"))
	serverKey, _ := ecdh.X25519().NewPrivateKey(sk[:])
	server := serverKey.PublicKey()
	zero := make([]byte, 32)
	empty := sha256.Sum256(nil)
	var acc []byte
	for i := 0; i < 300; i++ {
		k := sha256.Sum256([]byte(fmt.Sprintf("client %d", i)))
		priv, _ := ecdh.X25519().NewPrivateKey(k[:])
		share := priv.PublicKey().Bytes()
		shared, _ := priv.ECDH(server)
		th := sha256.Sum256(share)
		early, _ := hkdf.Extract(sha256.New, zero, zero)
		hs, _ := hkdf.Extract(sha256.New, shared, label(early, "derived", empty[:], 32))
		chs := label(hs, "c hs traffic", th[:], 32)
		shs := label(hs, "s hs traffic", th[:], 32)
		master, _ := hkdf.Extract(sha256.New, zero, label(hs, "derived", empty[:], 32))
		cap := label(master, "c ap traffic", th[:], 32)
		sap := label(master, "s ap traffic", th[:], 32)
		for _, s := range [][]byte{chs, shs, cap, sap} {
			b, _ := aes.NewCipher(label(s, "key", nil, 16))
			a, _ := cipher.NewGCM(b)
			label(s, "iv", nil, 12)
			if a.NonceSize() != 12 {
				return
			}
		}
		sf := mac(label(shs, "finished", nil, 32), th[:])
		acc = mac(label(chs, "finished", nil, 32), sf)
	}
	fmt.Println(hex.EncodeToString(acc))
}
