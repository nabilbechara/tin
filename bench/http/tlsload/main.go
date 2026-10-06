// tlsload measures TLS handshakes per second against a server (#472): C goroutines each open a
// TLS 1.3 connection, GET PATH with Connection: close, read the response and close, for D
// seconds. With -resume every goroutine keeps a session cache, so after its first connection
// each handshake resumes the session of the one before (a PSK and a new X25519 exchange, no
// certificate); without it every handshake is full. Certificates are not verified: this is a
// load generator, the servers' verification is checked elsewhere.
// Usage: tlsload -addr 127.0.0.1:9190 -path /plaintext -c 32 -d 5 [-resume]
// It prints one JSON line: {"handshakes": N, "resumed": R, "errors": E, "seconds": S, "rate": N/S}.
package main

import (
	"bufio"
	"crypto/tls"
	"encoding/json"
	"flag"
	"io"
	"net/http"
	"os"
	"sync"
	"sync/atomic"
	"time"
)

func main() {
	addr := flag.String("addr", "127.0.0.1:9190", "the server")
	path := flag.String("path", "/plaintext", "the path to GET")
	conns := flag.Int("c", 32, "concurrent connections")
	secs := flag.Float64("d", 5, "seconds to run")
	resume := flag.Bool("resume", false, "resume sessions (a session cache per goroutine)")
	flag.Parse()
	var done, resumed, errs atomic.Int64
	until := time.Now().Add(time.Duration(*secs * float64(time.Second)))
	start := time.Now()
	var wg sync.WaitGroup
	for i := 0; i < *conns; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			cfg := &tls.Config{InsecureSkipVerify: true, MinVersion: tls.VersionTLS13, ServerName: "localhost", NextProtos: []string{"http/1.1"}}
			if *resume {
				cfg.ClientSessionCache = tls.NewLRUClientSessionCache(4)
			}
			req := []byte("GET " + *path + " HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
			for time.Now().Before(until) {
				c, err := tls.Dial("tcp", *addr, cfg)
				if err != nil {
					errs.Add(1)
					continue
				}
				_, err = c.Write(req)
				if err == nil {
					var resp *http.Response
					resp, err = http.ReadResponse(bufio.NewReader(c), nil)
					if err == nil {
						_, err = io.Copy(io.Discard, resp.Body)
						resp.Body.Close()
						if err == nil && resp.StatusCode != 200 {
							err = io.ErrUnexpectedEOF
						}
					}
				}
				if err != nil {
					errs.Add(1)
				} else {
					done.Add(1)
					if c.ConnectionState().DidResume {
						resumed.Add(1)
					}
				}
				c.Close()
			}
		}()
	}
	wg.Wait()
	elapsed := time.Since(start).Seconds()
	json.NewEncoder(os.Stdout).Encode(map[string]any{"handshakes": done.Load(), "resumed": resumed.Load(),
		"errors": errs.Load(), "seconds": elapsed, "rate": float64(done.Load()) / elapsed})
}
