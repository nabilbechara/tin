// h2upstream is the Go net/http upstream of wire's HTTP/2 checks (#480): HTTPS (h2 and
// HTTP/1.1 by ALPN) on the first port and cleartext HTTP/2 by prior knowledge (h2c) or HTTP/1.1
// on the second. It counts the connections it accepts.
//
//	go run h2upstream.go TLS_PORT H2C_PORT CERT KEY
//
// Routes: / (the protocol), /echo (the body back), /trailers (gRPC-style trailers), /wait?ms=N,
// /conns (connections accepted so far), /big?n=N (N bytes).
package main

import (
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync/atomic"
	"time"
)

var conns atomic.Int64

func handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		fmt.Fprintf(w, "hello from go over %s", r.Proto)
	})
	mux.HandleFunc("/echo", func(w http.ResponseWriter, r *http.Request) {
		b, err := io.ReadAll(r.Body)
		if err != nil {
			http.Error(w, err.Error(), 500)
			return
		}
		w.Header().Set("Content-Type", r.Header.Get("Content-Type"))
		w.Header().Set("X-Got", r.Header.Get("X-Thing"))
		w.Write(b)
	})
	mux.HandleFunc("/trailers", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Trailer", "Grpc-Status, Grpc-Message")
		w.Header().Set("Content-Type", "application/grpc")
		w.Write([]byte("payload"))
		w.Header().Set("Grpc-Status", "0")
		w.Header().Set("Grpc-Message", "fine")
	})
	mux.HandleFunc("/wait", func(w http.ResponseWriter, r *http.Request) {
		ms, _ := strconv.Atoi(r.URL.Query().Get("ms"))
		time.Sleep(time.Duration(ms) * time.Millisecond)
		fmt.Fprintf(w, "waited %d", ms)
	})
	mux.HandleFunc("/conns", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintf(w, "%d", conns.Load())
	})
	mux.HandleFunc("/big", func(w http.ResponseWriter, r *http.Request) {
		n, _ := strconv.Atoi(r.URL.Query().Get("n"))
		w.Write([]byte(strings.Repeat("x", n)))
	})
	return mux
}

func count(c net.Conn, s http.ConnState) {
	if s == http.StateNew {
		conns.Add(1)
	}
}

func main() {
	tlsSrv := &http.Server{Addr: "127.0.0.1:" + os.Args[1], Handler: handler(), ConnState: count}
	plain := &http.Server{Addr: "127.0.0.1:" + os.Args[2], Handler: handler(), ConnState: count}
	plain.Protocols = new(http.Protocols)
	plain.Protocols.SetHTTP1(true)
	plain.Protocols.SetUnencryptedHTTP2(true)
	go func() {
		if err := plain.ListenAndServe(); err != nil {
			fmt.Println(err)
			os.Exit(1)
		}
	}()
	fmt.Println("listening")
	if err := tlsSrv.ListenAndServeTLS(os.Args[3], os.Args[4]); err != nil {
		fmt.Println(err)
		os.Exit(1)
	}
}
