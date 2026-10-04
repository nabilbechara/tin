// Go twin of tools/ci/fixtures/x509_mutate.tin: flips bytes of every certificate in each PEM file
// and prints the mutants crypto/x509 rejects.
package main

import (
	"crypto/x509"
	"encoding/pem"
	"fmt"
	"os"
)

func main() {
	for a := 1; a < len(os.Args); a++ {
		text, err := os.ReadFile(os.Args[a])
		if err != nil {
			fmt.Println(os.Args[a], err)
			continue
		}
		for k := 0; ; k++ {
			blk, rest := pem.Decode(text)
			if blk == nil {
				break
			}
			text = rest
			der := blk.Bytes
			accepted := 0
			for i := range der {
				for _, x := range []byte{0x01, 0x80, 0xff} {
					m := append([]byte{}, der...)
					m[i] ^= x
					if _, err := x509.ParseCertificate(m); err == nil {
						accepted++
					} else {
						fmt.Println(a, k, i, x, "rejected")
					}
				}
			}
			fmt.Println(a, k, "accepted", accepted)
		}
	}
}
