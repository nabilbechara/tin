// mtlspki writes the test PKI of the client-certificate checks (#475) into a directory, as PEM:
//
//	ca.pem                     the client CA (ECDSA P-256)
//	alice.pem, alice.key       a client certificate from it (ECDSA P-256, extended key usage clientAuth)
//	rsa.pem, rsa.key           a client certificate from it (RSA-2048, clientAuth)
//	dave.pem, dave.key         a client certificate from it (Ed25519, clientAuth; #477)
//	bob.pem, bob.key           a certificate from it for servers only (serverAuth)
//	carol.pem, carol.key       an expired client certificate from it
//	mallory.pem, mallory.key   a client certificate from another CA (other-ca.pem)
//
// Usage: go run mtlspki.go DIR
package main

import (
	"crypto"
	"crypto/ecdsa"
	"crypto/ed25519"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"math/big"
	"os"
	"path/filepath"
	"time"
)

var dir string
var serial int64

func write(name string, typ string, der []byte) {
	f, err := os.Create(filepath.Join(dir, name))
	if err != nil {
		panic(err)
	}
	defer f.Close()
	if err := pem.Encode(f, &pem.Block{Type: typ, Bytes: der}); err != nil {
		panic(err)
	}
}

func writeKey(name string, key crypto.Signer) {
	der, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		panic(err)
	}
	write(name, "PRIVATE KEY", der)
}

func ecKey() *ecdsa.PrivateKey {
	k, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		panic(err)
	}
	return k
}

// issue makes a certificate for cn with key pub, signed by parent's key (self-signed when parent
// is nil), and returns it.
func issue(cn string, pub crypto.PublicKey, parent *x509.Certificate, parentKey crypto.Signer, isCA bool,
	eku []x509.ExtKeyUsage, from, to time.Time) *x509.Certificate {
	serial++
	t := &x509.Certificate{
		SerialNumber:          big.NewInt(serial),
		Subject:               pkix.Name{CommonName: cn, Organization: []string{"tin tests"}},
		NotBefore:             from,
		NotAfter:              to,
		BasicConstraintsValid: true,
		IsCA:                  isCA,
		ExtKeyUsage:           eku,
		KeyUsage:              x509.KeyUsageDigitalSignature,
	}
	if isCA {
		t.KeyUsage = x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature
	}
	if parent == nil {
		parent = t
	}
	der, err := x509.CreateCertificate(rand.Reader, t, parent, pub, parentKey)
	if err != nil {
		panic(err)
	}
	c, err := x509.ParseCertificate(der)
	if err != nil {
		panic(err)
	}
	return c
}

func main() {
	dir = os.Args[1]
	now := time.Now()
	from, to := now.Add(-time.Hour), now.Add(30*24*time.Hour)
	client := []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}

	caKey := ecKey()
	ca := issue("tin test client CA", caKey.Public(), nil, caKey, true, nil, from, to)
	write("ca.pem", "CERTIFICATE", ca.Raw)

	ak := ecKey()
	write("alice.pem", "CERTIFICATE", issue("alice", ak.Public(), ca, caKey, false, client, from, to).Raw)
	writeKey("alice.key", ak)

	rk, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		panic(err)
	}
	write("rsa.pem", "CERTIFICATE", issue("rsa-client", rk.Public(), ca, caKey, false, client, from, to).Raw)
	writeKey("rsa.key", rk)

	_, dk, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		panic(err)
	}
	write("dave.pem", "CERTIFICATE", issue("dave", dk.Public(), ca, caKey, false, client, from, to).Raw)
	writeKey("dave.key", dk)

	bk := ecKey()
	write("bob.pem", "CERTIFICATE", issue("bob", bk.Public(), ca, caKey, false, []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}, from, to).Raw)
	writeKey("bob.key", bk)

	ck := ecKey()
	write("carol.pem", "CERTIFICATE", issue("carol", ck.Public(), ca, caKey, false, client, now.Add(-48*time.Hour), now.Add(-24*time.Hour)).Raw)
	writeKey("carol.key", ck)

	otherKey := ecKey()
	other := issue("another CA", otherKey.Public(), nil, otherKey, true, nil, from, to)
	write("other-ca.pem", "CERTIFICATE", other.Raw)
	mk := ecKey()
	write("mallory.pem", "CERTIFICATE", issue("mallory", mk.Public(), other, otherKey, false, client, from, to).Raw)
	writeKey("mallory.key", mk)
}
