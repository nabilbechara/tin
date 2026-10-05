// An HTTP/2 client for tools/ci/fixtures/h2.tin, run by tools/ci/h2_check.py (#360): Go's own
// HTTP/2 implementation (net/http: h2c by prior knowledge, or h2 over TLS by ALPN with -ca)
// against anvil's, with Huffman-coded headers and the dynamic table, request trailers, many
// streams at once and large bodies.
package main

import (
	"bytes"
	"crypto/tls"
	"crypto/x509"
	"flag"
	"fmt"
	"io"
	"math/rand"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

var base string
var client *http.Client

func fail(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "FAIL "+format+"\n", args...)
	os.Exit(1)
}

func pattern(n, start int) []byte {
	b := make([]byte, n)
	for i := range b {
		b[i] = byte((start + i) % 251)
	}
	return b
}

func sum(b []byte) int64 {
	var s int64
	for _, c := range b {
		s = (s*31 + int64(c)) % 1000000007
	}
	return s
}

func get(path string) (*http.Response, []byte) {
	resp, err := client.Get(base + path)
	if err != nil {
		fail("GET %s: %v", path, err)
	}
	body, err := io.ReadAll(resp.Body)
	resp.Body.Close()
	if err != nil {
		fail("GET %s body: %v", path, err)
	}
	if resp.ProtoMajor != 2 {
		fail("GET %s came over %s", path, resp.Proto)
	}
	return resp, body
}

func echo(body []byte, header map[string]string, trailer map[string]string) map[string]string {
	req, _ := http.NewRequest("POST", base+"/echo?k=v", bytes.NewReader(body))
	for k, v := range header {
		req.Header.Set(k, v)
	}
	if trailer != nil {
		// Trailers need a body of unknown length: the Go client sends them after the DATA frames.
		req.Body = io.NopCloser(bytes.NewReader(body))
		req.ContentLength = -1
		req.Trailer = http.Header{}
		for k, v := range trailer {
			req.Trailer.Set(k, v)
		}
	}
	resp, err := client.Do(req)
	if err != nil {
		fail("POST /echo: %v", err)
	}
	out, _ := io.ReadAll(resp.Body)
	resp.Body.Close()
	m := map[string]string{}
	for _, line := range strings.Split(string(out), "\n") {
		if k, v, ok := strings.Cut(line, "="); ok {
			m[k] = v
		}
	}
	return m
}

func main() {
	addr := flag.String("addr", "127.0.0.1:9360", "the server")
	ca := flag.String("ca", "", "HTTPS: the PEM file of the root that signed the server's certificate (h2 by ALPN)")
	flag.Parse()
	base = "http://" + *addr
	var p http.Protocols
	p.SetUnencryptedHTTP2(true)
	tr := &http.Transport{Protocols: &p, MaxConnsPerHost: 1}
	if *ca != "" {
		// HTTP/2 only: ALPN offers "h2" alone, so the server must choose it.
		pem, err := os.ReadFile(*ca)
		if err != nil {
			fail("ca: %v", err)
		}
		roots := x509.NewCertPool()
		if !roots.AppendCertsFromPEM(pem) {
			fail("ca: no certificate in %s", *ca)
		}
		base = "https://" + *addr
		p = http.Protocols{}
		p.SetHTTP2(true)
		tr.TLSClientConfig = &tls.Config{RootCAs: roots, MinVersion: tls.VersionTLS13}
	}
	client = &http.Client{Transport: tr, Timeout: 60 * time.Second}

	_, body := get("/")
	if string(body) != "hello from anvil over HTTP/2.0\n" {
		fail("GET / = %q", body)
	}
	if *ca != "" {
		fmt.Println("PASS GET / over h2 (TLS 1.3, ALPN) with Go's client")
	} else {
		fmt.Println("PASS GET / over h2c with Go's client")
	}

	m := echo([]byte("hi"), map[string]string{"X-Test": "a value", "Cookie": "a=1"}, nil)
	if m["proto"] != "HTTP/2.0" || m["len"] != "2" || m["x-test"] != "a value" || m["query"] != "k=v" || m["cookie"] != "a=1" {
		fail("echo %v", m)
	}
	big := pattern(1900000, 7) // past the 1 MiB stream window, under the check's TIN_MAX_BODY
	m = echo(big, nil, nil)
	if m["len"] != fmt.Sprint(len(big)) || m["sum"] != fmt.Sprint(sum(big)) {
		fail("1.9 MB echo %v", m)
	}
	fmt.Println("PASS headers, query and a 1.9 MB request body")

	m = echo([]byte("with trailers"), nil, map[string]string{"X-Trailer": "after the body"})
	if m["x-trailer"] != "after the body" || m["len"] != "13" {
		fail("request trailers %v", m)
	}
	fmt.Println("PASS request trailers reach q.Header")

	resp, body := get("/trailers?n=1000")
	var s int
	for _, c := range body {
		s += int(c)
	}
	if len(body) != 1000 || resp.Trailer.Get("X-Sum") != fmt.Sprint(s) || resp.Trailer.Get("Grpc-Status") != "0" {
		fail("trailers %d %v", len(body), resp.Trailer)
	}
	fmt.Println("PASS response trailers:", resp.Trailer.Get("X-Sum"), resp.Trailer.Get("Grpc-Status"))

	resp, body = get("/big?n=3000000")
	if !bytes.Equal(body, pattern(3000000, 0)) || resp.ContentLength != 3000000 {
		fail("big %d", len(body))
	}
	fmt.Println("PASS a 3 MB response within the flow-control windows")

	start := time.Now()
	resp, err := client.Get(base + "/stream?n=4&size=5000&ms=300")
	if err != nil {
		fail("stream: %v", err)
	}
	first := make([]byte, 5000)
	if _, err := io.ReadFull(resp.Body, first); err != nil || !bytes.Equal(first, pattern(5000, 0)) {
		fail("stream first write: %v", err)
	}
	early := time.Since(start)
	rest, _ := io.ReadAll(resp.Body)
	resp.Body.Close()
	if early > 250*time.Millisecond || !bytes.Equal(append(first, rest...), pattern(20000, 0)) {
		fail("stream: first write after %v, %d bytes", early, len(first)+len(rest))
	}
	fmt.Printf("PASS a streamed body: the first write came after %v, the whole after %v\n", early.Round(time.Millisecond), time.Since(start).Round(time.Millisecond))

	resp, err = client.Head(base + "/big?n=1234")
	if err != nil || resp.ContentLength != 1234 {
		fail("HEAD: %v %d", err, resp.ContentLength)
	}
	resp.Body.Close()
	fmt.Println("PASS HEAD")

	// Many streams at once on the one connection: waits overlap, bodies stay apart.
	start = time.Now()
	var wg sync.WaitGroup
	errs := make(chan string, 600)
	for i := 0; i < 600; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			switch i % 3 {
			case 0:
				_, b := get("/wait?ms=200")
				if string(b) != "waited 200" {
					errs <- fmt.Sprintf("wait %q", b)
				}
			case 1:
				b := pattern(rand.Intn(200000), i)
				m := echo(b, map[string]string{"X-Test": fmt.Sprint(i)}, nil)
				if m["len"] != fmt.Sprint(len(b)) || m["sum"] != fmt.Sprint(sum(b)) || m["x-test"] != fmt.Sprint(i) {
					errs <- fmt.Sprintf("echo %d %v", i, m)
				}
			default:
				n := 1000 + i*97
				_, b := get(fmt.Sprintf("/big?n=%d", n))
				if !bytes.Equal(b, pattern(n, 0)) {
					errs <- fmt.Sprintf("big %d", n)
				}
			}
		}(i)
	}
	wg.Wait()
	close(errs)
	for e := range errs {
		fail("concurrent: %s", e)
	}
	took := time.Since(start)
	if took > 10*time.Second {
		fail("600 requests took %v: the waits did not overlap", took)
	}
	fmt.Printf("PASS 600 requests on one connection (200 of them wait 200 ms) in %v\n", took.Round(time.Millisecond))
}
