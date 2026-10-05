// The Go net/http HTTP/2 baseline (#360): the /json and /plaintext endpoints of examples/api.tin,
// served over h2c (HTTP/2 without TLS, by prior knowledge) and HTTP/1.1 on one port, as anvil does.
package main

import (
	"encoding/json"
	"net/http"
	"os"
)

type Message struct {
	Message string `json:"message"`
}

func main() {
	addr := ":9182"
	if len(os.Args) > 1 {
		addr = os.Args[1]
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/json", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(Message{Message: "Hello, World!"})
	})
	mux.HandleFunc("/plaintext", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		w.Write([]byte("Hello, World!"))
	})
	var p http.Protocols
	p.SetHTTP1(true)
	p.SetUnencryptedHTTP2(true)
	srv := &http.Server{Addr: addr, Handler: mux, Protocols: &p}
	srv.ListenAndServe()
}
