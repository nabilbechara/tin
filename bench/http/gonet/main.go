// The Go net/http baseline: the same /json and /plaintext endpoints as examples/api.tin.
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
	addr := ":9181"
	if len(os.Args) > 1 {
		addr = os.Args[1]
	}
	http.HandleFunc("/json", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(Message{Message: "Hello, World!"})
	})
	http.HandleFunc("/plaintext", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		w.Write([]byte("Hello, World!"))
	})
	http.ListenAndServe(addr, nil)
}
