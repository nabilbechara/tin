// Go twin of toolchain/tests/v2/seal_sign.tin: private key parsing and signing with the test keys in
// toolchain/tests/data/keys. Run from the repository root:
//
//	go run ./bench/ref/seal_sign | sort        the twin's lines
//	go run ./bench/ref/seal_sign gen DIR       writes a fresh set of test keys (good and bad)
//	go run ./bench/ref/seal_sign verify DIR    reads "KEY SCHEME MSGHEX SIGHEX" lines on stdin and
//	                                           prints "KEY SCHEME ok|bad" (tools/ci/x509_check.py)
//
// Tin is stricter than Go in two places, applied here: RSA keys of 2048 to 8192 bits, and a
// public key inside a SEC 1 key must match the private scalar.
//
// The key files say "TESTING KEY" where PEM says "PRIVATE KEY" (as Go's own tests do), so that
// secret scanners leave them alone; both programs swap the words back before parsing.
package main

import (
	"bufio"
	"crypto"
	"crypto/ecdsa"
	"crypto/ed25519"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/rsa"
	_ "crypto/sha256"
	_ "crypto/sha512"
	"crypto/x509"
	"encoding/asn1"
	"encoding/hex"
	"encoding/pem"
	"fmt"
	"math/big"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// Good keys, in the order both programs print them.
var good = []string{"rsa2048-pkcs1", "rsa2048-pkcs8", "rsa3072-pkcs8", "rsa4096-pkcs1", "ec256-sec1", "ec256-pkcs8", "ec384-sec1", "ec384-pkcs8", "ed25519-pkcs8"}

// Bad keys: each must fail to parse.
var bad = []string{"rsa1024-pkcs1", "ec521-pkcs8", "ec256-wrong-public", "rsa2048-wrong-crt", "rsa2048-wrong-n", "rsa2048-truncated", "encrypted"}

var message = []byte("Tin signing test message")

func check(err error) {
	if err != nil {
		panic(err)
	}
}

func write(dir, name, typ string, der []byte) {
	text := string(pem.EncodeToMemory(&pem.Block{Type: typ, Bytes: der}))
	text = strings.ReplaceAll(text, "PRIVATE KEY", "TESTING KEY")
	check(os.WriteFile(filepath.Join(dir, name+".pem"), []byte(text), 0o644))
}

type pkcs1 struct {
	Version                     int
	N, E, D, P, Q, Dp, Dq, Qinv *big.Int
}

type sec1 struct {
	Version    int
	PrivateKey []byte
	Curve      asn1.ObjectIdentifier `asn1:"optional,explicit,tag:0"`
	PublicKey  asn1.BitString        `asn1:"optional,explicit,tag:1"`
}

func rsaDER(k *rsa.PrivateKey, qinv, n *big.Int) []byte {
	der, err := asn1.Marshal(pkcs1{0, n, big.NewInt(int64(k.E)), k.D, k.Primes[0], k.Primes[1],
		k.Precomputed.Dp, k.Precomputed.Dq, qinv})
	check(err)
	return der
}

func gen(dir string) {
	check(os.MkdirAll(dir, 0o755))
	for _, bits := range []int{1024, 2048, 3072, 4096} {
		k, err := rsa.GenerateKey(rand.Reader, bits)
		check(err)
		p8, err := x509.MarshalPKCS8PrivateKey(k)
		check(err)
		switch bits {
		case 1024:
			write(dir, "rsa1024-pkcs1", "RSA PRIVATE KEY", x509.MarshalPKCS1PrivateKey(k))
		case 2048:
			der := x509.MarshalPKCS1PrivateKey(k)
			write(dir, "rsa2048-pkcs1", "RSA PRIVATE KEY", der)
			write(dir, "rsa2048-pkcs8", "PRIVATE KEY", p8)
			write(dir, "rsa2048-truncated", "RSA PRIVATE KEY", der[:len(der)-10])
			write(dir, "rsa2048-wrong-crt", "RSA PRIVATE KEY", rsaDER(k, new(big.Int).Add(k.Precomputed.Qinv, big.NewInt(1)), k.N))
			write(dir, "rsa2048-wrong-n", "RSA PRIVATE KEY", rsaDER(k, k.Precomputed.Qinv, new(big.Int).Add(k.N, big.NewInt(2))))
		case 3072:
			write(dir, "rsa3072-pkcs8", "PRIVATE KEY", p8)
		case 4096:
			write(dir, "rsa4096-pkcs1", "RSA PRIVATE KEY", x509.MarshalPKCS1PrivateKey(k))
		}
	}
	for _, c := range []struct {
		name  string
		curve elliptic.Curve
	}{{"ec256", elliptic.P256()}, {"ec384", elliptic.P384()}, {"ec521", elliptic.P521()}} {
		k, err := ecdsa.GenerateKey(c.curve, rand.Reader)
		check(err)
		p8, err := x509.MarshalPKCS8PrivateKey(k)
		check(err)
		write(dir, c.name+"-pkcs8", "PRIVATE KEY", p8)
		if c.name == "ec521" {
			continue
		}
		s1, err := x509.MarshalECPrivateKey(k)
		check(err)
		write(dir, c.name+"-sec1", "EC PRIVATE KEY", s1)
		if c.name == "ec256" {
			other, err := ecdsa.GenerateKey(c.curve, rand.Reader)
			check(err)
			pub, err := other.PublicKey.ECDH()
			check(err)
			b := pub.Bytes()
			der, err := asn1.Marshal(sec1{1, k.D.FillBytes(make([]byte, 32)), asn1.ObjectIdentifier{1, 2, 840, 10045, 3, 1, 7},
				asn1.BitString{Bytes: b, BitLength: 8 * len(b)}})
			check(err)
			write(dir, "ec256-wrong-public", "EC PRIVATE KEY", der)
		}
	}
	_, ek, err := ed25519.GenerateKey(rand.Reader)
	check(err)
	p8, err := x509.MarshalPKCS8PrivateKey(ek)
	check(err)
	write(dir, "ed25519-pkcs8", "PRIVATE KEY", p8)
	write(dir, "encrypted", "ENCRYPTED PRIVATE KEY", []byte("not a key"))
}

func load(dir, name string) (crypto.Signer, error) {
	b, err := os.ReadFile(filepath.Join(dir, name+".pem"))
	check(err)
	blk, _ := pem.Decode([]byte(strings.ReplaceAll(string(b), "TESTING KEY", "PRIVATE KEY")))
	switch blk.Type {
	case "RSA PRIVATE KEY":
		k, err := x509.ParsePKCS1PrivateKey(blk.Bytes)
		if err != nil {
			return nil, err
		}
		return k, rsaRules(k)
	case "EC PRIVATE KEY":
		k, err := x509.ParseECPrivateKey(blk.Bytes)
		if err != nil {
			return nil, err
		}
		return k, ecRules(k, blk.Bytes)
	case "PRIVATE KEY":
		k, err := x509.ParsePKCS8PrivateKey(blk.Bytes)
		if err != nil {
			return nil, err
		}
		switch k := k.(type) {
		case *rsa.PrivateKey:
			return k, rsaRules(k)
		case *ecdsa.PrivateKey:
			if k.Curve == elliptic.P521() {
				return nil, fmt.Errorf("Tin signs on P-256 and P-384 only")
			}
			return k, nil
		case ed25519.PrivateKey:
			return k, nil
		}
		return nil, fmt.Errorf("Tin signs with RSA, ECDSA and Ed25519 keys only")
	}
	return nil, fmt.Errorf("unsupported PEM block %s", blk.Type)
}

// ecRules is Tin's extra rule for SEC 1 keys: a public key given in the file must match.
func ecRules(k *ecdsa.PrivateKey, der []byte) error {
	var s sec1
	if _, err := asn1.Unmarshal(der, &s); err != nil {
		return err
	}
	if len(s.PublicKey.Bytes) == 0 {
		return nil
	}
	pub, err := k.PublicKey.ECDH()
	check(err)
	if string(pub.Bytes()) != string(s.PublicKey.Bytes) {
		return fmt.Errorf("public key does not match")
	}
	return nil
}

// rsaRules is Tin's extra rule: RSA keys of 2048 to 8192 bits.
func rsaRules(k *rsa.PrivateKey) error {
	if b := k.N.BitLen(); b < 2048 || b > 8192 {
		return fmt.Errorf("RSA key size %d", b)
	}
	return nil
}

func digest(h crypto.Hash, msg []byte) []byte {
	d := h.New()
	d.Write(msg)
	return d.Sum(nil)
}

func main() {
	dir := "toolchain/tests/data/keys"
	if len(os.Args) > 2 && os.Args[1] == "gen" {
		gen(os.Args[2])
		return
	}
	if len(os.Args) > 2 && os.Args[1] == "verify" {
		verify(os.Args[2])
		return
	}
	for _, name := range good {
		k, err := load(dir, name)
		if err != nil {
			fmt.Println(name, "ERROR", err)
			continue
		}
		switch k := k.(type) {
		case *rsa.PrivateKey:
			fmt.Println(name, "RSA", k.N.BitLen())
			for _, h := range []crypto.Hash{crypto.SHA256, crypto.SHA384, crypto.SHA512} {
				sig, err := rsa.SignPKCS1v15(nil, k, h, digest(h, message))
				check(err)
				fmt.Println(name, "pkcs1", h, hex.EncodeToString(sig))
				pss, err := rsa.SignPSS(rand.Reader, k, h, digest(h, message), &rsa.PSSOptions{SaltLength: rsa.PSSSaltLengthEqualsHash})
				check(err)
				ok := rsa.VerifyPSS(&k.PublicKey, h, digest(h, message), pss, &rsa.PSSOptions{SaltLength: h.Size()}) == nil
				fmt.Println(name, "pss", h, ok)
			}
		case *ecdsa.PrivateKey:
			fmt.Println(name, "ECDSA", k.Curve.Params().Name)
			for _, h := range []crypto.Hash{crypto.SHA256, crypto.SHA384, crypto.SHA512} {
				sig, err := k.Sign(nil, digest(h, message), h)
				check(err)
				fmt.Println(name, "ecdsa", h, hex.EncodeToString(sig))
			}
		case ed25519.PrivateKey:
			fmt.Println(name, "Ed25519")
			fmt.Println(name, "ed25519", hex.EncodeToString(ed25519.Sign(k, message)))
		}
	}
	// SignTLS: which schemes each kind of key may sign (TLS 1.3 binds ECDSA curves to schemes).
	for _, name := range []string{"rsa2048-pkcs8", "ec256-sec1", "ec384-pkcs8", "ed25519-pkcs8"} {
		for _, scheme := range []int{0x0401, 0x0804, 0x0805, 0x0806, 0x0809, 0x0403, 0x0503, 0x0603, 0x0807} {
			ok := false
			switch {
			case strings.HasPrefix(name, "rsa"):
				ok = scheme >= 0x0804 && scheme <= 0x0806
			case strings.HasPrefix(name, "ec256"):
				ok = scheme == 0x0403
			case strings.HasPrefix(name, "ec384"):
				ok = scheme == 0x0503
			case strings.HasPrefix(name, "ed25519"):
				ok = scheme == 0x0807
			}
			fmt.Println("signtls", name, scheme, ok)
		}
	}
	for _, name := range bad {
		_, err := load(dir, name)
		fmt.Println(name, "rejected", err != nil)
	}
}

// verify checks signatures made by Tin: "KEY SCHEME MSGHEX SIGHEX" on stdin.
func verify(dir string) {
	sc := bufio.NewScanner(os.Stdin)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	for sc.Scan() {
		f := strings.Fields(sc.Text())
		if len(f) != 4 {
			continue
		}
		k, err := load(dir, f[0])
		check(err)
		scheme, _ := strconv.Atoi(f[1])
		msg, _ := hex.DecodeString(f[2])
		sig, _ := hex.DecodeString(f[3])
		h := map[int]crypto.Hash{0x0804: crypto.SHA256, 0x0805: crypto.SHA384, 0x0806: crypto.SHA512, 0x0403: crypto.SHA256, 0x0503: crypto.SHA384}[scheme]
		ok := false
		switch k := k.(type) {
		case *rsa.PrivateKey:
			ok = rsa.VerifyPSS(&k.PublicKey, h, digest(h, msg), sig, &rsa.PSSOptions{SaltLength: h.Size()}) == nil
		case *ecdsa.PrivateKey:
			ok = ecdsa.VerifyASN1(&k.PublicKey, digest(h, msg), sig)
		case ed25519.PrivateKey:
			ok = ed25519.Verify(k.Public().(ed25519.PublicKey), msg, sig)
		}
		res := "bad"
		if ok {
			res = "ok"
		}
		fmt.Println(f[0], f[1], res)
	}
}
