// Generates the X.509 test PKI: certificates under DIR/certs and DIR/cases.txt listing every
// verification case and its expected outcome. Used by tools/ci/x509_check.py (a fresh PKI per
// run) and to make the checked-in copy under toolchain/tests/data/x509.
//
//	go run ./bench/ref/x509_pki DIR
//
// tls_sigs.txt: "CERT SCHEME MSGHEX SIGHEX" lines, TLS 1.3 signatures by the named certificate's key.
//
// cases.txt: a "now UNIX" line, then one line per case:
//
//	NAME HOST|- USAGE LEAF INTERMEDIATES|- ROOTS EXPECT
//
// USAGE is server, client or any; INTERMEDIATES and ROOTS are comma-separated certificate
// names (DIR/certs/NAME.pem); EXPECT is "OK n" (chain length) or a failure class.
package main

import (
	"crypto"
	"crypto/ecdsa"
	"crypto/ed25519"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/rsa"
	_ "crypto/sha256"
	_ "crypto/sha512"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/asn1"
	"encoding/pem"
	"fmt"
	"math/big"
	"net"
	"os"
	"path/filepath"
	"strings"
	"time"
)

var (
	dir    string
	now    = time.Date(2030, 6, 1, 0, 0, 0, 0, time.UTC)
	serial int64
	certs  = map[string]*x509.Certificate{}
	keys   = map[string]crypto.Signer{}
	lines  []string
)

func rsaKey(bits int) crypto.Signer {
	k, err := rsa.GenerateKey(rand.Reader, bits)
	check(err)
	return k
}

func check(err error) {
	if err != nil {
		panic(err)
	}
}

type spec struct {
	name, cn   string
	issuer     string // "" = self-signed
	key        crypto.Signer
	ca         bool
	noBC       bool
	pathLen    int // -1 = none
	ku         x509.KeyUsage
	eku        []x509.ExtKeyUsage
	dns        []string
	ips        []string
	from, to   time.Time
	alg        x509.SignatureAlgorithm
	permitted  []string
	excluded   []string
	critical   bool
	corruptSig bool
}

// make1 creates and stores one certificate.
func make1(s spec) {
	serial++
	if s.key == nil {
		s.key = rsaKey(2048)
	}
	if s.from.IsZero() {
		s.from = time.Date(2020, 1, 1, 0, 0, 0, 0, time.UTC)
	}
	if s.to.IsZero() {
		s.to = time.Date(2090, 1, 1, 0, 0, 0, 0, time.UTC)
	}
	t := &x509.Certificate{
		SerialNumber:          big.NewInt(serial),
		Subject:               pkix.Name{CommonName: s.cn, Organization: []string{"Tin Test PKI"}},
		NotBefore:             s.from,
		NotAfter:              s.to,
		KeyUsage:              s.ku,
		ExtKeyUsage:           s.eku,
		DNSNames:              s.dns,
		BasicConstraintsValid: !s.noBC,
		IsCA:                  s.ca,
		SignatureAlgorithm:    s.alg,
		PermittedDNSDomains:   s.permitted,
		ExcludedDNSDomains:    s.excluded,
	}
	if s.pathLen >= 0 && s.ca {
		t.MaxPathLen = s.pathLen
		t.MaxPathLenZero = s.pathLen == 0
	} else {
		t.MaxPathLen = -1
	}
	for _, ip := range s.ips {
		t.IPAddresses = append(t.IPAddresses, net.ParseIP(ip))
	}
	if s.critical {
		t.ExtraExtensions = append(t.ExtraExtensions, pkix.Extension{Id: asn1.ObjectIdentifier{1, 3, 6, 1, 4, 1, 99999, 1}, Critical: true, Value: []byte{0x05, 0x00}})
	}
	parent, pkey := t, s.key
	if s.issuer != "" {
		parent, pkey = certs[s.issuer], keys[s.issuer]
	}
	der, err := x509.CreateCertificate(rand.Reader, t, parent, s.key.Public(), pkey)
	check(err)
	if s.corruptSig {
		der[len(der)-1] ^= 0x55
	}
	c, err := x509.ParseCertificate(der)
	check(err)
	certs[s.name], keys[s.name] = c, s.key
	write(s.name, der)
}

func write(name string, der []byte) {
	f, err := os.Create(filepath.Join(dir, "certs", name+".pem"))
	check(err)
	check(pem.Encode(f, &pem.Block{Type: "CERTIFICATE", Bytes: der}))
	check(f.Close())
}

func ca(name, issuer string, mod func(*spec)) {
	s := spec{name: name, cn: "Tin Test " + name, issuer: issuer, ca: true, pathLen: -1, ku: x509.KeyUsageCertSign | x509.KeyUsageCRLSign}
	if mod != nil {
		mod(&s)
	}
	make1(s)
}

func leaf(name, issuer string, mod func(*spec)) {
	s := spec{name: name, cn: "www.example.com", issuer: issuer, pathLen: -1,
		ku:   x509.KeyUsageDigitalSignature,
		eku:  []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		dns:  []string{"example.com", "*.example.com"},
		ips:  []string{"192.0.2.1", "2001:db8::1"},
		from: time.Date(2029, 1, 1, 0, 0, 0, 0, time.UTC), to: time.Date(2031, 1, 1, 0, 0, 0, 0, time.UTC)}
	if mod != nil {
		mod(&s)
	}
	make1(s)
}

func add(name, host, usage, leaf, inter, roots, expect string) {
	lines = append(lines, strings.Join([]string{name, host, usage, leaf, inter, roots, expect}, " "))
}

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: x509_pki DIR")
		os.Exit(2)
	}
	dir = os.Args[1]
	check(os.MkdirAll(filepath.Join(dir, "certs"), 0o755))

	ca("root", "", nil)
	ca("root2", "", nil)
	ca("inter", "root", nil)
	leaf("leaf", "inter", nil)
	add("good", "www.example.com", "server", "leaf", "inter", "root", "OK 3")
	add("good-apex", "example.com", "server", "leaf", "inter", "root", "OK 3")
	add("good-case-and-dot", "WWW.Example.COM.", "server", "leaf", "inter", "root", "OK 3")
	add("good-ipv4", "192.0.2.1", "server", "leaf", "inter", "root", "OK 3")
	add("good-ipv6", "[2001:db8::1]", "server", "leaf", "inter", "root", "OK 3")
	add("good-no-host", "-", "server", "leaf", "inter", "root", "OK 3")
	add("good-any-usage", "-", "any", "leaf", "inter", "root", "OK 3")
	add("good-extra-roots", "www.example.com", "server", "leaf", "inter", "root2,root", "OK 3")
	add("wrong-host", "evil.com", "server", "leaf", "inter", "root", "hostname")
	add("wildcard-two-labels", "a.b.example.com", "server", "leaf", "inter", "root", "hostname")
	add("wildcard-suffix-only", "wwwexample.com", "server", "leaf", "inter", "root", "hostname")
	add("wrong-ipv4", "192.0.2.2", "server", "leaf", "inter", "root", "hostname")
	add("ip-as-dns", "example.com.192.0.2.1", "server", "leaf", "inter", "root", "hostname")
	add("untrusted-root", "www.example.com", "server", "leaf", "inter", "root2", "unknown-authority")
	add("missing-intermediate", "www.example.com", "server", "leaf", "-", "root", "unknown-authority")
	add("wrong-usage", "www.example.com", "client", "leaf", "inter", "root", "eku")

	leaf("leaf-cn-only", "inter", func(s *spec) { s.cn = "example.com"; s.dns = nil; s.ips = nil })
	add("common-name-ignored", "example.com", "server", "leaf-cn-only", "inter", "root", "hostname")

	leaf("leaf-expired", "inter", func(s *spec) { s.to = time.Date(2030, 1, 1, 0, 0, 0, 0, time.UTC) })
	add("expired-leaf", "www.example.com", "server", "leaf-expired", "inter", "root", "time")
	leaf("leaf-future", "inter", func(s *spec) { s.from = time.Date(2030, 7, 1, 0, 0, 0, 0, time.UTC) })
	add("not-yet-valid-leaf", "www.example.com", "server", "leaf-future", "inter", "root", "time")

	ca("inter-expired", "root", func(s *spec) { s.to = time.Date(2029, 12, 1, 0, 0, 0, 0, time.UTC) })
	leaf("leaf-under-expired", "inter-expired", nil)
	add("expired-intermediate", "www.example.com", "server", "leaf-under-expired", "inter-expired", "root", "time")

	ca("root-expired", "", func(s *spec) { s.to = time.Date(2029, 12, 1, 0, 0, 0, 0, time.UTC) })
	ca("inter-under-expired-root", "root-expired", nil)
	leaf("leaf-expired-root", "inter-under-expired-root", nil)
	add("expired-root", "www.example.com", "server", "leaf-expired-root", "inter-under-expired-root", "root-expired", "time")

	leaf("leaf-badsig", "inter", func(s *spec) { s.corruptSig = true })
	add("bad-signature", "www.example.com", "server", "leaf-badsig", "inter", "root", "signature")

	// Same subject as "inter" but a different key: the leaf it signed does not verify under "inter".
	ca("inter-impostor", "root", func(s *spec) { s.cn = "Tin Test inter" })
	leaf("leaf-by-impostor", "inter-impostor", nil)
	add("signed-by-other-key", "www.example.com", "server", "leaf-by-impostor", "inter", "root", "signature")

	ca("inter-not-ca", "root", func(s *spec) { s.ca = false; s.ku = x509.KeyUsageDigitalSignature })
	leaf("leaf-under-not-ca", "inter-not-ca", nil)
	add("non-ca-intermediate", "www.example.com", "server", "leaf-under-not-ca", "inter-not-ca", "root", "not-ca")

	ca("inter-no-bc", "root", func(s *spec) { s.ca = false; s.noBC = true })
	leaf("leaf-under-no-bc", "inter-no-bc", nil)
	add("intermediate-without-basic-constraints", "www.example.com", "server", "leaf-under-no-bc", "inter-no-bc", "root", "not-ca")

	ca("inter-no-certsign", "root", func(s *spec) { s.ku = x509.KeyUsageDigitalSignature })
	leaf("leaf-under-no-certsign", "inter-no-certsign", nil)
	add("intermediate-without-cert-sign", "www.example.com", "server", "leaf-under-no-certsign", "inter-no-certsign", "root", "not-ca")

	leaf("leaf-sha1", "inter", func(s *spec) { s.alg = x509.SHA1WithRSA })
	add("sha1-signature", "www.example.com", "server", "leaf-sha1", "inter", "root", "sha1")

	ca("inter-sha1", "root", func(s *spec) { s.alg = x509.SHA1WithRSA })
	leaf("leaf-under-sha1", "inter-sha1", nil)
	add("sha1-intermediate", "www.example.com", "server", "leaf-under-sha1", "inter-sha1", "root", "sha1")

	ca("inter-pss", "root", func(s *spec) { s.alg = x509.SHA256WithRSAPSS })
	leaf("leaf-pss", "inter-pss", func(s *spec) { s.alg = x509.SHA256WithRSAPSS })
	add("good-pss", "www.example.com", "server", "leaf-pss", "inter-pss", "root", "OK 3")

	ecKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	check(err)
	leaf("leaf-ec-key", "inter", func(s *spec) { s.key = ecKey })
	add("good-ecdsa-leaf-key", "www.example.com", "server", "leaf-ec-key", "inter", "root", "OK 3")
	for _, c := range []elliptic.Curve{elliptic.P384(), elliptic.P521()} {
		k, err := ecdsa.GenerateKey(c, rand.Reader)
		check(err)
		n := "leaf-ec-key-" + c.Params().Name
		leaf(n, "inter", func(s *spec) { s.key = k })
		add("good-"+strings.ToLower(c.Params().Name)+"-leaf-key", "www.example.com", "server", n, "inter", "root", "OK 3")
	}

	ca("inter-small", "root", func(s *spec) { s.key = rsaKey(1024) })
	leaf("leaf-under-small", "inter-small", nil)
	add("rsa-1024-intermediate", "www.example.com", "server", "leaf-under-small", "inter-small", "root", "weak-key")

	// A chain of 9 intermediates: 11 certificates, over the default limit of 8.
	prev := "root"
	names := []string{}
	for i := 1; i <= 9; i++ {
		n := fmt.Sprintf("long%d", i)
		ca(n, prev, nil)
		names = append([]string{n}, names...)
		prev = n
	}
	leaf("leaf-long", prev, nil)
	add("chain-too-long", "www.example.com", "server", "leaf-long", strings.Join(names, ","), "root", "too-long")
	add("chain-at-limit", "-", "server", "long4", "long3,long2,long1", "root", "OK 5")

	ca("inter-pathlen0", "root", func(s *spec) { s.pathLen = 0 })
	ca("inter-below-pathlen0", "inter-pathlen0", nil)
	leaf("leaf-pathlen", "inter-below-pathlen0", nil)
	add("path-length-exceeded", "www.example.com", "server", "leaf-pathlen", "inter-below-pathlen0,inter-pathlen0", "root", "pathlen")
	leaf("leaf-under-pathlen0", "inter-pathlen0", nil)
	add("path-length-ok", "www.example.com", "server", "leaf-under-pathlen0", "inter-pathlen0", "root", "OK 3")

	leaf("leaf-client", "inter", func(s *spec) { s.eku = []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth} })
	add("leaf-client-only", "www.example.com", "server", "leaf-client", "inter", "root", "eku")
	ca("inter-client", "root", func(s *spec) { s.eku = []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth} })
	leaf("leaf-under-client", "inter-client", nil)
	add("intermediate-client-only", "www.example.com", "server", "leaf-under-client", "inter-client", "root", "eku")

	ca("inter-permit", "root", func(s *spec) { s.permitted = []string{"example.com"} })
	leaf("leaf-permitted", "inter-permit", nil)
	add("name-constraint-permitted", "www.example.com", "server", "leaf-permitted", "inter-permit", "root", "OK 3")
	leaf("leaf-not-permitted", "inter-permit", func(s *spec) { s.dns = []string{"www.other.com"}; s.ips = nil })
	add("name-constraint-not-permitted", "www.other.com", "server", "leaf-not-permitted", "inter-permit", "root", "constraints")
	ca("inter-exclude", "root", func(s *spec) { s.excluded = []string{"example.com"} })
	leaf("leaf-excluded", "inter-exclude", nil)
	add("name-constraint-excluded", "www.example.com", "server", "leaf-excluded", "inter-exclude", "root", "constraints")

	leaf("leaf-critical", "inter", func(s *spec) { s.critical = true })
	add("unhandled-critical-extension", "www.example.com", "server", "leaf-critical", "inter", "root", "critical")

	leaf("self-signed", "", func(s *spec) { s.issuer = "" })
	add("self-signed-trusted", "www.example.com", "server", "self-signed", "-", "self-signed", "OK 1")
	add("self-signed-untrusted", "www.example.com", "server", "self-signed", "-", "root", "unknown-authority")

	// Two intermediates with the same subject and key: one expired, one valid; the builder must find the valid one.
	k := rsaKey(2048)
	ca("inter-twin-old", "root", func(s *spec) { s.cn = "Tin Test twin"; s.key = k; s.to = time.Date(2029, 1, 1, 0, 0, 0, 0, time.UTC) })
	ca("inter-twin-new", "root", func(s *spec) { s.cn = "Tin Test twin"; s.key = k })
	leaf("leaf-twin", "inter-twin-new", nil)
	add("expired-and-valid-issuer", "www.example.com", "server", "leaf-twin", "inter-twin-old,inter-twin-new", "root", "OK 3")

	// ECDSA chains: P-256 root, P-384 intermediate; and an ECDSA intermediate under the RSA root.
	ecRootKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	check(err)
	ecInterKey, err := ecdsa.GenerateKey(elliptic.P384(), rand.Reader)
	check(err)
	ca("ec-root", "", func(s *spec) { s.key = ecRootKey; s.alg = x509.ECDSAWithSHA256 })
	ca("ec-inter", "ec-root", func(s *spec) { s.key = ecInterKey; s.alg = x509.ECDSAWithSHA256 })
	leaf("leaf-under-ec", "ec-inter", func(s *spec) { s.alg = x509.ECDSAWithSHA384 })
	add("good-ecdsa-chain", "www.example.com", "server", "leaf-under-ec", "ec-inter", "ec-root", "OK 3")
	leaf("leaf-ec-sha512", "ec-inter", func(s *spec) { s.alg = x509.ECDSAWithSHA512 })
	add("good-ecdsa-sha512", "www.example.com", "server", "leaf-ec-sha512", "ec-inter", "ec-root", "OK 3")
	leaf("leaf-ec-badsig", "ec-inter", func(s *spec) { s.alg = x509.ECDSAWithSHA384; s.corruptSig = true })
	add("bad-ecdsa-signature", "www.example.com", "server", "leaf-ec-badsig", "ec-inter", "ec-root", "signature")
	leaf("leaf-ec-sha1", "ec-inter", func(s *spec) { s.alg = x509.ECDSAWithSHA1 })
	add("ecdsa-sha1-signature", "www.example.com", "server", "leaf-ec-sha1", "ec-inter", "ec-root", "sha1")
	k256, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	check(err)
	ca("inter-ec-under-rsa", "root", func(s *spec) { s.key = k256 })
	leaf("leaf-under-ec-rsa", "inter-ec-under-rsa", func(s *spec) { s.alg = x509.ECDSAWithSHA256 })
	add("good-rsa-root-ecdsa-intermediate", "www.example.com", "server", "leaf-under-ec-rsa", "inter-ec-under-rsa", "root", "OK 3")
	add("ecdsa-intermediate-wrong-root", "www.example.com", "server", "leaf-under-ec-rsa", "inter-ec-under-rsa", "ec-root", "unknown-authority")

	// Ed25519: a root, an intermediate and a leaf, and an Ed25519 leaf key under the RSA chain.
	edRoot, edRootKey, err := ed25519.GenerateKey(rand.Reader)
	check(err)
	_ = edRoot
	_, edInterKey, err := ed25519.GenerateKey(rand.Reader)
	check(err)
	_, edLeafKey, err := ed25519.GenerateKey(rand.Reader)
	check(err)
	ca("ed-root", "", func(s *spec) { s.key = edRootKey; s.alg = x509.PureEd25519 })
	ca("ed-inter", "ed-root", func(s *spec) { s.key = edInterKey; s.alg = x509.PureEd25519 })
	leaf("leaf-under-ed", "ed-inter", func(s *spec) { s.key = edLeafKey; s.alg = x509.PureEd25519 })
	add("good-ed25519-chain", "www.example.com", "server", "leaf-under-ed", "ed-inter", "ed-root", "OK 3")
	leaf("leaf-ed-badsig", "ed-inter", func(s *spec) { s.alg = x509.PureEd25519; s.corruptSig = true })
	add("bad-ed25519-signature", "www.example.com", "server", "leaf-ed-badsig", "ed-inter", "ed-root", "signature")
	add("ed25519-wrong-root", "www.example.com", "server", "leaf-under-ed", "ed-inter", "root", "unknown-authority")

	// TLS 1.3 CertificateVerify-style RSA-PSS signatures by the leaf's key (salt = hash length).
	var sigs []string
	msg := []byte(strings.Repeat(" ", 64) + "TLS 1.3, server CertificateVerify\x00transcript")
	for _, sc := range []struct {
		code int
		h    crypto.Hash
	}{{0x0804, crypto.SHA256}, {0x0805, crypto.SHA384}, {0x0806, crypto.SHA512}} {
		d := sc.h.New()
		d.Write(msg)
		sig, err := rsa.SignPSS(rand.Reader, keys["leaf"].(*rsa.PrivateKey), sc.h, d.Sum(nil), &rsa.PSSOptions{SaltLength: rsa.PSSSaltLengthEqualsHash})
		check(err)
		sigs = append(sigs, fmt.Sprintf("leaf %d %x %x", sc.code, msg, sig))
	}
	// ECDSA signatures (0x0403 with P-256 and SHA-256, 0x0503 with P-384 and SHA-384).
	for _, sc := range []struct {
		cert string
		code int
		h    crypto.Hash
	}{{"leaf-ec-key", 0x0403, crypto.SHA256}, {"leaf-ec-key-P-384", 0x0503, crypto.SHA384}} {
		d := sc.h.New()
		d.Write(msg)
		sig, err := ecdsa.SignASN1(rand.Reader, keys[sc.cert].(*ecdsa.PrivateKey), d.Sum(nil))
		check(err)
		sigs = append(sigs, fmt.Sprintf("%s %d %x %x", sc.cert, sc.code, msg, sig))
	}
	edSig := ed25519.Sign(edLeafKey, msg)
	sigs = append(sigs, fmt.Sprintf("leaf-under-ed %d %x %x", 0x0807, msg, edSig))
	check(os.WriteFile(filepath.Join(dir, "tls_sigs.txt"), []byte(strings.Join(sigs, "\n")+"\n"), 0o644))

	out := fmt.Sprintf("now %d\n%s\n", now.Unix(), strings.Join(lines, "\n"))
	check(os.WriteFile(filepath.Join(dir, "cases.txt"), []byte(out), 0o644))
}
