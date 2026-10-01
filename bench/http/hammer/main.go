// hammer is a wrk-style HTTP/1.1 load generator: C keep-alive connections, each sending
// one request at a time (no pipelining unless -pipeline), latency per request in a
// microsecond histogram. Output: requests/s, p50, p90, p99, p99.9, max, errors.
package main

import (
	"bufio"
	"bytes"
	"flag"
	"fmt"
	"net"
	"os"
	"runtime"
	"strconv"
	"sync"
	"sync/atomic"
	"time"
)

const buckets = 2_000_000 // 1µs buckets up to 2s

func main() {
	addr := flag.String("addr", "127.0.0.1:9180", "host:port")
	path := flag.String("path", "/json", "request path")
	conns := flag.Int("c", 100, "connections")
	dur := flag.Duration("d", 10*time.Second, "duration")
	warm := flag.Duration("w", 2*time.Second, "warmup (not measured)")
	threads := flag.Int("t", 4, "OS threads for the client (GOMAXPROCS)")
	pipe := flag.Int("pipeline", 1, "requests in flight per connection")
	flag.Parse()
	runtime.GOMAXPROCS(*threads)
	req := []byte("GET " + *path + " HTTP/1.1\r\nHost: " + *addr + "\r\nUser-Agent: hammer\r\nAccept: */*\r\n\r\n")
	batch := bytes.Repeat(req, *pipe)

	var measuring atomic.Bool
	var stop atomic.Bool
	var total atomic.Int64
	hists := make([][]uint32, *conns)
	var wg sync.WaitGroup
	for i := 0; i < *conns; i++ {
		hists[i] = make([]uint32, 4096)
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			h := hists[i]
			big := map[int]uint32{}
			defer func() { bigs.Store(i, big) }()
			// Connect slowly enough for the macOS accept backlog (kern.ipc.somaxconn); a
			// connection reset before measuring starts is retried, not counted.
			time.Sleep(time.Duration(i/100) * 10 * time.Millisecond)
			for !stop.Load() {
				c, err := net.Dial("tcp", *addr)
				if err != nil {
					if measuring.Load() {
						dialErrs.Add(1)
						return
					}
					time.Sleep(time.Duration(5+i%20) * time.Millisecond)
					continue
				}
				c.(*net.TCPConn).SetNoDelay(true)
				r := bufio.NewReaderSize(c, 65536)
				for !stop.Load() {
					t0 := time.Now()
					if _, err = c.Write(batch); err == nil {
						for k := 0; k < *pipe && err == nil; k++ {
							err = readResponse(r)
						}
					}
					if err != nil {
						break
					}
					us := int(time.Since(t0) / time.Microsecond)
					if measuring.Load() {
						total.Add(int64(*pipe))
						if us < len(h) {
							h[us] += uint32(*pipe)
						} else {
							big[us] += uint32(*pipe)
						}
					}
				}
				c.Close()
				if err != nil && !stop.Load() {
					if measuring.Load() {
						noteErr(err)
						return
					}
					continue
				}
			}
		}(i)
	}
	time.Sleep(*warm)
	measuring.Store(true)
	start := time.Now()
	time.Sleep(*dur)
	measuring.Store(false)
	el := time.Since(start)
	stop.Store(true)
	wg.Wait()

	all := map[int]uint64{}
	for i := range hists {
		for us, n := range hists[i] {
			if n > 0 {
				all[us] += uint64(n)
			}
		}
	}
	bigs.Range(func(_, v any) bool {
		for us, n := range v.(map[int]uint32) {
			all[us] += uint64(n)
		}
		return true
	})
	n := uint64(total.Load())
	pct := func(p float64) float64 {
		want := uint64(float64(n) * p)
		var seen uint64
		for us := 0; us < buckets; us++ {
			seen += all[us]
			if seen >= want && seen > 0 {
				return float64(us) / 1000
			}
		}
		return -1
	}
	maxUs := 0
	for us := range all {
		if us > maxUs {
			maxUs = us
		}
	}
	fmt.Printf("%-10s %8.0f req/s  p50 %.3fms  p90 %.3fms  p99 %.3fms  p99.9 %.3fms  max %.3fms  errors %d  dial-fail %d  (c=%d, %s)\n",
		*path, float64(n)/el.Seconds(), pct(0.50), pct(0.90), pct(0.99), pct(0.999), float64(maxUs)/1000, errs.Load(), dialErrs.Load(), *conns, el.Round(time.Millisecond))
	if errs.Load() > 0 {
		fmt.Println("first error:", firstErr.Load())
		os.Exit(1)
	}
}

var bigs sync.Map
var errs atomic.Int64
var dialErrs atomic.Int64
var firstErr atomic.Value

func noteErr(err error) {
	errs.Add(1)
	firstErr.CompareAndSwap(nil, err.Error())
}

// readResponse consumes one response: status line, headers, Content-Length body.
func readResponse(r *bufio.Reader) error {
	line, err := r.ReadSlice('\n')
	if err != nil {
		return err
	}
	if len(line) < 12 || line[9] != '2' {
		return fmt.Errorf("bad status: %q", line)
	}
	cl := -1
	for {
		l, err := r.ReadSlice('\n')
		if err != nil {
			return err
		}
		if len(l) <= 2 {
			break
		}
		if len(l) > 16 && (l[0] == 'C' || l[0] == 'c') && bytes.EqualFold(l[:15], []byte("content-length:")) {
			v := bytes.TrimSpace(l[15:])
			cl, _ = strconv.Atoi(string(v))
		}
	}
	if cl < 0 {
		return fmt.Errorf("no content-length")
	}
	_, err = r.Discard(cl)
	return err
}
