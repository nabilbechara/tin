// The Go net/http client twin of bench/http/wire_load.tin (#480): N GETs of URL from C goroutines
// at once (N/C each), over HTTP/2 by prior knowledge (one connection) or HTTP/1.1 (C kept
// connections). It prints "N ERRORS NANOSECONDS".
package main

import (
	"flag"
	"fmt"
	"io"
	"net/http"
	"sync"
	"sync/atomic"
	"time"
)

func main() {
	url := flag.String("url", "http://127.0.0.1:9182/plaintext", "the URL")
	n := flag.Int("n", 20000, "requests")
	c := flag.Int("c", 100, "concurrent callers")
	mode := flag.String("mode", "h2c", "h2c or h1")
	flag.Parse()
	t := &http.Transport{MaxIdleConnsPerHost: *c, MaxIdleConns: *c}
	t.Protocols = new(http.Protocols)
	if *mode == "h2c" {
		t.Protocols.SetUnencryptedHTTP2(true)
	} else {
		t.Protocols.SetHTTP1(true)
	}
	client := &http.Client{Transport: t, Timeout: 30 * time.Second}
	var errors atomic.Int64
	var wg sync.WaitGroup
	start := time.Now()
	per := *n / *c
	for i := 0; i < *c; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for k := 0; k < per; k++ {
				r, err := client.Get(*url)
				if err != nil {
					errors.Add(1)
					continue
				}
				b, _ := io.ReadAll(r.Body)
				r.Body.Close()
				if r.StatusCode != 200 || string(b) != "Hello, World!" {
					errors.Add(1)
				}
			}
		}()
	}
	wg.Wait()
	fmt.Printf("%d %d %d\n", per**c, errors.Load(), time.Since(start).Nanoseconds())
}
