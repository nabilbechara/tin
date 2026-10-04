// Go twin of tests/v2/seal_wycheproof.tin: run from the repository root, `go run ./bench/ref/seal_wycheproof | sort`.
package main

import (
	"crypto"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/sha512"
	"hash"
	"crypto/x509"
	"encoding/hex"
	"fmt"
	"math/big"
	"os"
	"strconv"
	"strings"
)

var files = []string{
	"rsa_signature_2048_sha256", "rsa_signature_2048_sha384", "rsa_signature_2048_sha512", "rsa_signature_3072_sha256",
	"rsa_signature_4096_sha256", "rsa_signature_4096_sha384", "rsa_signature_4096_sha512",
	"rsa_pss_2048_sha256_mgf1_0", "rsa_pss_2048_sha256_mgf1_32", "rsa_pss_2048_sha384_mgf1_48",
	"rsa_pss_4096_sha256_mgf1_32", "rsa_pss_4096_sha512_mgf1_64", "rsa_pss_misc",
}

func unhex(s string) []byte {
	if s == "-" {
		return nil
	}
	b, _ := hex.DecodeString(s)
	return b
}

var hashes = map[string]crypto.Hash{"SHA-256": crypto.SHA256, "SHA-384": crypto.SHA384, "SHA-512": crypto.SHA512}

func digestOf(h crypto.Hash, msg []byte) []byte {
	var d hash.Hash
	switch h {
	case crypto.SHA384:
		d = sha512.New384()
	case crypto.SHA512:
		d = sha512.New()
	default:
		d = sha256.New()
	}
	d.Write(msg)
	return d.Sum(nil)
}

// pssSaltLen recovers the salt length of a PSS signature that verified (MGF1 over the same hash).
func pssSaltLen(key *rsa.PublicKey, h crypto.Hash, sig []byte) int {
	m := new(big.Int).Exp(new(big.Int).SetBytes(sig), big.NewInt(int64(key.E)), key.N)
	emBits := key.N.BitLen() - 1
	emLen := (emBits + 7) / 8
	em := m.FillBytes(make([]byte, emLen))
	hlen := h.Size()
	dbLen := emLen - hlen - 1
	hh := em[dbLen : dbLen+hlen]
	var mask []byte
	for c := 0; len(mask) < dbLen; c++ {
		mask = append(mask, digestOf(h, append(append([]byte{}, hh...), byte(c>>24), byte(c>>16), byte(c>>8), byte(c)))...)
	}
	db := make([]byte, dbLen)
	for i := range db {
		db[i] = em[i] ^ mask[i]
	}
	db[0] &= 0xff >> uint(8*emLen-emBits)
	at := 0
	for at < dbLen && db[at] == 0 {
		at++
	}
	return dbLen - at - 1
}

func run(name string) {
	text, err := os.ReadFile("tests/wycheproof/rsa/" + name + ".txt")
	if err != nil {
		fmt.Println(name, "unreadable:", err)
		return
	}
	kind, salt, h := "", -1, crypto.SHA256
	var key *rsa.PublicKey
	counts, passed := map[string]int{}, map[string]int{}
	for _, ln := range strings.Split(string(text), "\n") {
		if ln == "" || ln[0] == '#' {
			continue
		}
		f := strings.Fields(ln)
		if f[0] == "group" {
			kind, salt, h = f[1], -1, hashes[f[2]]
			if f[3] != "-" {
				salt, _ = strconv.Atoi(f[3])
			}
			key, err = x509.ParsePKCS1PublicKey(unhex(f[4]))
			if err != nil {
				key = nil
			}
			continue
		}
		result := f[1]
		digest := digestOf(h, unhex(f[2]))
		sig := unhex(f[3])
		ok := false
		if key != nil {
			if kind == "rsa-pkcs1" {
				ok = rsa.VerifyPKCS1v15(key, h, digest, sig) == nil
			} else {
				// Go reads salt length 0 as "auto"; Tin checks it exactly, so check it here too.
				ok = rsa.VerifyPSS(key, h, digest, sig, &rsa.PSSOptions{SaltLength: salt}) == nil
				if ok && salt == 0 {
					ok = pssSaltLen(key, h, sig) == 0
				}
			}
		}
		counts[result]++
		if ok {
			passed[result]++
		}
		if (result == "valid" && !ok) || (result == "invalid" && ok) {
			fmt.Println(name, "MISMATCH tcId", f[0], result, ok)
		}
	}
	fmt.Println(name, "valid", passed["valid"], "/", counts["valid"], "invalid-accepted", passed["invalid"], "/", counts["invalid"], "acceptable-accepted", passed["acceptable"], "/", counts["acceptable"])
}

func main() {
	for _, name := range files {
		run(name)
	}
}
