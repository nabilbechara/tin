// Go twin of tests/v2/seal_certinfo.tin: parsed certificate fields, IP parsing, PEM decoding and
// host name matching. Run from the repository root: `go run ./bench/ref/seal_certinfo | sort`.
//
// Differences from Go handled here: seal.ParseIP accepts brackets and keeps IPv4 in 4 bytes, a
// PEM error anywhere fails seal.DecodePEM, MaxPathLen is -1 without basic constraints, and in host
// names a wildcard needs two labels after "*." and a host containing "*" never matches.
package main

import (
	"crypto"
	"crypto/ecdsa"
	"crypto/ed25519"
	"crypto/rsa"
	_ "crypto/sha256"
	_ "crypto/sha512"
	"crypto/x509"
	"encoding/hex"
	"encoding/pem"
	"fmt"
	"net"
	"os"
	"strconv"
	"strings"
)

var names = []string{"root", "inter", "leaf", "leaf-pss", "inter-pss", "leaf-ec-key", "leaf-ec-key-P-384",
	"leaf-ec-key-P-521", "inter-pathlen0", "inter-permit", "inter-exclude", "leaf-client", "inter-not-ca",
	"inter-no-bc", "inter-no-certsign", "leaf-critical", "leaf-cn-only", "leaf-sha1", "self-signed", "ec-root", "ec-inter",
	"leaf-under-ec", "leaf-ec-sha1", "ed-root", "leaf-under-ed"}

func join(xs []string) string {
	if len(xs) == 0 {
		return "-"
	}
	return strings.Join(xs, ",")
}

var algNames = map[x509.SignatureAlgorithm]string{
	x509.SHA1WithRSA: "SHA1WithRSA", x509.SHA256WithRSA: "SHA256WithRSA", x509.SHA384WithRSA: "SHA384WithRSA",
	x509.SHA512WithRSA: "SHA512WithRSA", x509.SHA256WithRSAPSS: "SHA256WithRSAPSS", x509.SHA384WithRSAPSS: "SHA384WithRSAPSS",
	x509.SHA512WithRSAPSS: "SHA512WithRSAPSS", x509.ECDSAWithSHA1: "ECDSAWithSHA1", x509.ECDSAWithSHA256: "ECDSAWithSHA256",
	x509.ECDSAWithSHA384: "ECDSAWithSHA384", x509.ECDSAWithSHA512: "ECDSAWithSHA512", x509.PureEd25519: "PureEd25519",
}

var ekuOIDs = map[x509.ExtKeyUsage]string{
	x509.ExtKeyUsageAny: "2.5.29.37.0", x509.ExtKeyUsageServerAuth: "1.3.6.1.5.5.7.3.1", x509.ExtKeyUsageClientAuth: "1.3.6.1.5.5.7.3.2",
}

func show(name string) {
	text, err := os.ReadFile("tests/data/x509/certs/" + name + ".pem")
	if err != nil {
		panic(err)
	}
	blk, _ := pem.Decode(text)
	c, err := x509.ParseCertificate(blk.Bytes)
	if err != nil {
		fmt.Println(name, "ERROR", err)
		return
	}
	key, curve, bits := "UnknownKey", "", 0
	switch k := c.PublicKey.(type) {
	case *rsa.PublicKey:
		key, bits = "RSA", k.N.BitLen()
	case *ecdsa.PublicKey:
		key, curve = "ECDSA", k.Curve.Params().Name
	case ed25519.PublicKey:
		key = "Ed25519"
	}
	serial := c.SerialNumber.Bytes()
	if len(serial) == 0 || serial[0]&0x80 != 0 {
		serial = append([]byte{0}, serial...)
	}
	fmt.Println(name, "v", c.Version, "cn", fmt.Sprintf("%q", c.Subject.CommonName), "o", join(c.Subject.Organization),
		"issuer", fmt.Sprintf("%q", c.Issuer.CommonName), "nb", c.NotBefore.Unix(), "na", c.NotAfter.Unix())
	fmt.Println(name, "alg", algNames[c.SignatureAlgorithm], "key", key, "curve", curve, "bits", bits,
		"siglen", len(c.Signature), "serial", hex.EncodeToString(serial))
	var eku, crit, ips []string
	for _, u := range c.ExtKeyUsage {
		eku = append(eku, ekuOIDs[u])
	}
	for _, o := range c.UnknownExtKeyUsage {
		eku = append(eku, o.String())
	}
	for _, o := range c.UnhandledCriticalExtensions {
		crit = append(crit, o.String())
	}
	for _, ip := range c.IPAddresses {
		ips = append(ips, hex.EncodeToString(ip))
	}
	pathlen := c.MaxPathLen
	if !c.BasicConstraintsValid {
		pathlen = -1 // Go leaves 0 without basic constraints; Tin always writes "none" as -1.
	}
	fmt.Println(name, "bc", c.BasicConstraintsValid, "ca", c.IsCA, "pathlen", pathlen, "ku", int(c.KeyUsage),
		"eku", join(eku), "critical", join(crit))
	fmt.Println(name, "dns", join(c.DNSNames), "ip", join(ips), "permit", join(c.PermittedDNSDomains),
		"exclude", join(c.ExcludedDNSDomains), "skid", len(c.SubjectKeyId), "akid", len(c.AuthorityKeyId))
}

func tlsSigs() {
	lines, _ := os.ReadFile("tests/data/x509/tls_sigs.txt")
	for _, ln := range strings.Split(strings.TrimSpace(string(lines)), "\n") {
		f := strings.Fields(ln)
		text, _ := os.ReadFile("tests/data/x509/certs/" + f[0] + ".pem")
		blk, _ := pem.Decode(text)
		c, err := x509.ParseCertificate(blk.Bytes)
		if err != nil {
			panic(err)
		}
		scheme, _ := strconv.Atoi(f[1])
		msg, _ := hex.DecodeString(f[2])
		sig, _ := hex.DecodeString(f[3])
		verify := func(sc int) bool {
			if k, ok := c.PublicKey.(ed25519.PublicKey); ok {
				return sc == 0x0807 && ed25519.Verify(k, msg, sig)
			}
			if sc == 0x0807 {
				return false
			}
			h := map[int]crypto.Hash{0x0804: crypto.SHA256, 0x0805: crypto.SHA384, 0x0806: crypto.SHA512, 0x0403: crypto.SHA256, 0x0503: crypto.SHA384}[sc]
			d := h.New()
			d.Write(msg)
			switch k := c.PublicKey.(type) {
			case *rsa.PublicKey:
				return sc >= 0x0804 && sc <= 0x0806 && rsa.VerifyPSS(k, h, d.Sum(nil), sig, &rsa.PSSOptions{SaltLength: rsa.PSSSaltLengthEqualsHash}) == nil
			case *ecdsa.PublicKey:
				// TLS 1.3 binds the curve to the scheme.
				want := map[int]string{0x0403: "P-256", 0x0503: "P-384"}[sc]
				return k.Curve.Params().Name == want && ecdsa.VerifyASN1(k, d.Sum(nil), sig)
			}
			return false
		}
		other := 0x0804
		switch scheme {
		case 0x0804:
			other = 0x0805
		case 0x0403:
			other = 0x0503
		case 0x0503, 0x0807:
			other = 0x0403
		}
		e1 := verify(scheme)
		e4 := verify(other)
		msg[len(msg)-1] ^= 1
		e2 := verify(scheme)
		msg[len(msg)-1] ^= 1
		sig[len(sig)-1] ^= 1
		e3 := verify(scheme)
		fmt.Println("tls", f[0], scheme, e1, e2, e3, e4)
	}
}

func main() {
	for _, n := range names {
		show(n)
	}
	for _, s := range []string{"192.0.2.1", "0.0.0.0", "255.255.255.255", "256.1.1.1", "1.2.3", "1.2.3.4.5", "01.2.3.4",
		"1.2.3.04", "1..2.3", "::", "::1", "2001:db8::1", "[2001:db8::1]", "2001:db8:0:0:0:0:0:1", "1:2:3:4:5:6:7:8",
		"1:2:3:4:5:6:7:8:9", "1::2::3", ":1", "1:", "::ffff:1.2.3.4", "fe80::1%eth0", "12345::", "g::1", "", "example.com"} {
		t := s
		if len(t) > 2 && t[0] == '[' && t[len(t)-1] == ']' {
			t = t[1 : len(t)-1]
		}
		ip := net.ParseIP(t)
		if ip != nil && !strings.Contains(t, ":") {
			ip = ip.To4()
		}
		if ip == nil {
			fmt.Println("ip", fmt.Sprintf("%q", s), "nil")
		} else {
			fmt.Println("ip", fmt.Sprintf("%q", s), hex.EncodeToString(ip))
		}
	}
	pems := []string{
		"-----BEGIN A-----\nAAEC\n-----END A-----\n",
		"junk\n-----BEGIN A-----\r\nAA\r\nEC\r\n-----END A-----\r\nmore\n-----BEGIN B-----\n-----END B-----\n",
		"-----BEGIN A-----\nAAEC\n",
		"-----BEGIN A-----\nAAEC\n-----END B-----\n",
		"-----BEGIN A-----\nA!EC\n-----END A-----\n",
		"no blocks here",
	}
	for i, p := range pems {
		rest := []byte(p)
		var parts []string
		for {
			b, r := pem.Decode(rest)
			if b == nil {
				break
			}
			rest = r
			parts = append(parts, b.Type+"="+hex.EncodeToString(b.Bytes))
		}
		if strings.Contains(string(rest), "-----BEGIN") {
			fmt.Println("pem", i, "error")
			continue
		}
		fmt.Println("pem", i, len(parts), join(parts))
	}
	tlsSigs()
	patterns := []string{"example.com", "*.example.com", "EXAMPLE.org.", "*.com", "w*.example.com", "*.*.example.com", "*", "a.*.example.com", "xn--bcher-kva.example"}
	hosts := []string{"example.com", "www.example.com", "a.b.example.com", ".example.com", "example.org", "Example.ORG", "foo.com", "www.example.com.", "wx.example.com", "xn--bcher-kva.example", "*.example.com"}
	for _, p := range patterns {
		c := &x509.Certificate{DNSNames: []string{p}}
		for _, h := range hosts {
			ok := c.VerifyHostname(h) == nil
			// Tin: "*." needs at least two labels after it ("*.com" matches nothing).
			if lp := strings.ToLower(p); strings.HasPrefix(lp, "*.") && strings.Count(lp[1:], ".") < 2 {
				ok = false
			}
			// Tin: a host containing "*" never matches (Go compares it literally).
			if strings.Contains(h, "*") {
				ok = false
			}
			fmt.Println("host", fmt.Sprintf("%q", p), fmt.Sprintf("%q", h), ok)
		}
	}
}
