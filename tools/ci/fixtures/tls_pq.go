// tls_pq is the Go side of the post-quantum key exchange checks (#479) in tls_check.py and
// tls_server_check.py. It prints the group crypto/tls negotiated.
//
//	go run tls_pq.go server PORT CERT KEY GROUPS   serve "ok" on 127.0.0.1:PORT, print each connection's group
//	go run tls_pq.go client ADDR CAFILE GROUPS     connect, print the group
//
// GROUPS is a comma-separated list of X25519MLKEM768, X25519 and P-256, in preference order.
package main

import (
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"net"
	"os"
	"strings"
)

func groups(list string) []tls.CurveID {
	var out []tls.CurveID
	for _, g := range strings.Split(list, ",") {
		switch g {
		case "X25519MLKEM768":
			out = append(out, tls.X25519MLKEM768)
		case "X25519":
			out = append(out, tls.X25519)
		case "P-256":
			out = append(out, tls.CurveP256)
		default:
			panic("unknown group " + g)
		}
	}
	return out
}

func main() {
	switch os.Args[1] {
	case "server":
		cert, err := tls.LoadX509KeyPair(os.Args[3], os.Args[4])
		if err != nil {
			panic(err)
		}
		cfg := &tls.Config{Certificates: []tls.Certificate{cert}, CurvePreferences: groups(os.Args[5]), MinVersion: tls.VersionTLS13}
		ln, err := tls.Listen("tcp", "127.0.0.1:"+os.Args[2], cfg)
		if err != nil {
			panic(err)
		}
		fmt.Println("listening")
		for {
			c, err := ln.Accept()
			if err != nil {
				panic(err)
			}
			go func(c net.Conn) {
				defer c.Close()
				tc := c.(*tls.Conn)
				if err := tc.Handshake(); err != nil {
					fmt.Println("handshake:", err)
					return
				}
				fmt.Println("group", tc.ConnectionState().CurveID)
				buf := make([]byte, 4096)
				tc.Read(buf)
				tc.Write([]byte("HTTP/1.0 200 OK\r\n\r\nok"))
			}(c)
		}
	case "client":
		pem, err := os.ReadFile(os.Args[3])
		if err != nil {
			panic(err)
		}
		pool := x509.NewCertPool()
		pool.AppendCertsFromPEM(pem)
		cfg := &tls.Config{RootCAs: pool, ServerName: "localhost", CurvePreferences: groups(os.Args[4])}
		c, err := tls.Dial("tcp", os.Args[2], cfg)
		if err != nil {
			fmt.Println("fault", err)
			return
		}
		defer c.Close()
		c.Write([]byte("GET /fast HTTP/1.0\r\n\r\n"))
		buf := make([]byte, 4096)
		n, _ := c.Read(buf)
		fmt.Println("group", c.ConnectionState().CurveID, strings.HasSuffix(string(buf[:n]), "fast") || n > 0)
	}
}
