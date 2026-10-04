// Go twin of tests/v2/seal_x509.tin: verifies every case of a test PKI made by bench/ref/x509_pki
// with crypto/x509 and prints "NAME OK n" or "NAME FAIL class", one line per case.
//
//	go run ./bench/ref/seal_x509 [DIR]   (default tests/data/x509)
//
// Tin is stricter than Go in two places, applied here explicitly so the outputs agree: a chain
// may hold at most 8 certificates, and RSA keys need at least 2048 bits.
package main

import (
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

var dir = "tests/data/x509"

func load(name string) *x509.Certificate {
	b, err := os.ReadFile(filepath.Join(dir, "certs", name+".pem"))
	if err != nil {
		panic(err)
	}
	blk, _ := pem.Decode(b)
	c, err := x509.ParseCertificate(blk.Bytes)
	if err != nil {
		panic(err)
	}
	return c
}

func pool(list string) *x509.CertPool {
	p := x509.NewCertPool()
	if list != "-" {
		for _, n := range strings.Split(list, ",") {
			p.AddCert(load(n))
		}
	}
	return p
}

func class(err error) string {
	var he x509.HostnameError
	var ie x509.CertificateInvalidError
	var ue x509.UnknownAuthorityError
	var ce x509.UnhandledCriticalExtension
	switch {
	case errors.As(err, &he):
		return "hostname"
	case errors.As(err, &ie):
		switch ie.Reason {
		case x509.Expired:
			return "time"
		case x509.NotAuthorizedToSign:
			return "not-ca"
		case x509.TooManyIntermediates:
			return "pathlen"
		case x509.CANotAuthorizedForThisName:
			return "constraints"
		case x509.IncompatibleUsage, x509.CANotAuthorizedForExtKeyUsage:
			return "eku"
		}
	case errors.As(err, &ce):
		return "critical"
	case errors.As(err, &ue):
		hint := fmt.Sprint(ue)
		if strings.Contains(hint, "possibly because of") {
			if strings.Contains(hint, "insecure algorithm") {
				return "sha1"
			}
			if strings.Contains(hint, "cannot sign this kind of certificate") {
				return "not-ca"
			}
			return "signature"
		}
		return "unknown-authority"
	}
	return "other: " + err.Error()
}

// tinRules applies Tin's extra checks to a chain Go accepted.
func tinRules(chain []*x509.Certificate) string {
	if len(chain) > 8 {
		return "too-long"
	}
	for i, c := range chain {
		if i > 0 {
			if k, ok := c.PublicKey.(*rsa.PublicKey); ok && k.N.BitLen() < 2048 {
				return "weak-key"
			}
		}
	}
	return ""
}

func main() {
	if len(os.Args) > 1 {
		dir = os.Args[1]
	}
	text, err := os.ReadFile(filepath.Join(dir, "cases.txt"))
	if err != nil {
		panic(err)
	}
	var now time.Time
	for _, ln := range strings.Split(strings.TrimSpace(string(text)), "\n") {
		f := strings.Fields(ln)
		if f[0] == "now" {
			sec, _ := strconv.ParseInt(f[1], 10, 64)
			now = time.Unix(sec, 0).UTC()
			continue
		}
		opts := x509.VerifyOptions{Intermediates: pool(f[4]), Roots: pool(f[5]), CurrentTime: now}
		if f[1] != "-" {
			opts.DNSName = f[1]
		}
		switch f[2] {
		case "server":
			opts.KeyUsages = []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}
		case "client":
			opts.KeyUsages = []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}
		default:
			opts.KeyUsages = []x509.ExtKeyUsage{x509.ExtKeyUsageAny}
		}
		chains, err := load(f[3]).Verify(opts)
		if err != nil {
			fmt.Println(f[0], "FAIL", class(err))
			continue
		}
		best := chains[0]
		for _, c := range chains {
			if len(c) < len(best) {
				best = c
			}
		}
		if why := tinRules(best); why != "" {
			fmt.Println(f[0], "FAIL", why)
			continue
		}
		fmt.Println(f[0], "OK", len(best))
	}
}
