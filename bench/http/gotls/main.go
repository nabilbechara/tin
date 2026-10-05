// The Go crypto/tls baseline for bench/http/https.tin: net/http over TLS 1.3 only, HTTP/1.1
// only (no h2), no session tickets (the Tin server issues none, so every new connection is a
// full handshake on both sides), with the same /plaintext and /big?n=N endpoints.
// Usage: gotls ADDR CERT KEY
package main

import (
	"crypto/tls"
	"net/http"
	"os"
	"strconv"
)

func main() {
	addr, cert, key := ":9191", "cert.pem", "key.pem"
	if len(os.Args) > 3 {
		addr, cert, key = os.Args[1], os.Args[2], os.Args[3]
	}
	big := make([]byte, 1<<20)
	for i := range big {
		big[i] = byte(i % 251)
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/plaintext", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		w.Write([]byte("Hello, World!"))
	})
	mux.HandleFunc("/big", func(w http.ResponseWriter, r *http.Request) {
		n, err := strconv.Atoi(r.URL.Query().Get("n"))
		if err != nil || n < 0 || n > len(big) {
			n = len(big)
		}
		w.Header().Set("Content-Type", "application/octet-stream")
		w.Write(big[:n])
	})
	srv := &http.Server{
		Addr:         addr,
		Handler:      mux,
		TLSConfig:    &tls.Config{MinVersion: tls.VersionTLS13, SessionTicketsDisabled: true, NextProtos: []string{"http/1.1"}},
		TLSNextProto: map[string]func(*http.Server, *tls.Conn, http.Handler){},
	}
	if err := srv.ListenAndServeTLS(cert, key); err != nil {
		os.Stderr.WriteString(err.Error() + "\n")
		os.Exit(1)
	}
}
