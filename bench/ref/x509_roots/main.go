// Prints "roots N": how many certificates of the PEM file crypto/x509 parses, the count
// tools/ci/fixtures/x509_roots.tin must match for seal.SystemRoots.
package main

import (
	"crypto/x509"
	"encoding/pem"
	"fmt"
	"os"
)

func main() {
	text, err := os.ReadFile(os.Args[1])
	if err != nil {
		panic(err)
	}
	n := 0
	for {
		blk, rest := pem.Decode(text)
		if blk == nil {
			break
		}
		text = rest
		if blk.Type != "CERTIFICATE" {
			continue
		}
		if _, err := x509.ParseCertificate(blk.Bytes); err == nil {
			n++
		}
	}
	fmt.Println("roots", n)
}
