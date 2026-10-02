// conformance runs HTTP/1.1 edge cases against an anvil server and prints PASS/FAIL
// per case. Stdlib only. Usage: conformance -addr 127.0.0.1:9200 [-pid N] [-heavy] [-reqs 2000000]
package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
)

var addr string
var passed, failed int

func result(name string, ok bool, format string, a ...any) {
	tag := "PASS"
	if ok {
		passed++
	} else {
		failed++
		tag = "FAIL"
	}
	fmt.Printf("%s %-30s %s\n", tag, name, fmt.Sprintf(format, a...))
}

type resp struct {
	status  int
	headers map[string]string
	body    []byte
}

// readResp consumes one response: status line, headers, Content-Length body (skipped for HEAD).
func readResp(r *bufio.Reader, head bool) (*resp, error) {
	line, err := r.ReadString('\n')
	if err != nil {
		return nil, err
	}
	line = strings.TrimRight(line, "\r\n")
	parts := strings.SplitN(line, " ", 3)
	if len(parts) < 2 || !strings.HasPrefix(parts[0], "HTTP/1.") {
		return nil, fmt.Errorf("bad status line %q", line)
	}
	st, err := strconv.Atoi(parts[1])
	if err != nil {
		return nil, fmt.Errorf("bad status %q", line)
	}
	rs := &resp{status: st, headers: map[string]string{}}
	for {
		l, err := r.ReadString('\n')
		if err != nil {
			return nil, err
		}
		l = strings.TrimRight(l, "\r\n")
		if l == "" {
			break
		}
		k, v, ok := strings.Cut(l, ":")
		if !ok {
			return nil, fmt.Errorf("bad header %q", l)
		}
		rs.headers[strings.ToLower(k)] = strings.TrimSpace(v)
	}
	cl, ok := rs.headers["content-length"]
	if !ok {
		return nil, fmt.Errorf("no content-length")
	}
	n, err := strconv.Atoi(cl)
	if err != nil || n < 0 {
		return nil, fmt.Errorf("bad content-length %q", cl)
	}
	if head {
		return rs, nil
	}
	rs.body = make([]byte, n)
	if _, err := io.ReadFull(r, rs.body); err != nil {
		return nil, err
	}
	return rs, nil
}

func dial() (net.Conn, *bufio.Reader, error) {
	c, err := net.DialTimeout("tcp", addr, 5*time.Second)
	if err != nil {
		return nil, nil, err
	}
	c.SetDeadline(time.Now().Add(20 * time.Second))
	return c, bufio.NewReaderSize(c, 1<<16), nil
}

func isReset(err error) bool {
	return errors.Is(err, syscall.ECONNRESET) || errors.Is(err, syscall.EPIPE)
}

// closedSoon reports whether the server closes the connection (EOF or reset) within d.
func closedSoon(c net.Conn, r *bufio.Reader, d time.Duration) (bool, string) {
	c.SetReadDeadline(time.Now().Add(d))
	b := make([]byte, 64)
	n, err := r.Read(b)
	if err == io.EOF || isReset(err) {
		return true, "closed"
	}
	if err != nil {
		return false, "still open: " + err.Error()
	}
	return false, fmt.Sprintf("still open, got %d extra bytes %q", n, b[:n])
}

// roundTrip sends raw on a fresh connection and reads one response.
func roundTrip(raw string, head bool) (*resp, net.Conn, *bufio.Reader, error) {
	c, r, err := dial()
	if err != nil {
		return nil, nil, nil, err
	}
	if _, err := c.Write([]byte(raw)); err != nil {
		c.Close()
		return nil, nil, nil, err
	}
	rs, err := readResp(r, head)
	if err != nil {
		c.Close()
		return nil, nil, nil, err
	}
	return rs, c, r, nil
}

func get(path string) (*resp, error) {
	rs, c, _, err := roundTrip("GET "+path+" HTTP/1.1\r\nHost: x\r\n\r\n", false)
	if err != nil {
		return nil, err
	}
	c.Close()
	return rs, nil
}

type echo struct {
	Path   string `json:"path"`
	Query  string `json:"query"`
	Name   string `json:"name"`
	Agent  string `json:"agent"`
	Length int    `json:"length"`
}

func echoOf(rs *resp) (echo, error) {
	var e echo
	err := json.Unmarshal(rs.body, &e)
	return e, err
}

const jsonBody = `{"message":"Hello, World!"}`

// alive checks the server still answers a plain request after a hostile case.
func alive() bool {
	rs, err := get("/json")
	return err == nil && rs.status == 200 && string(rs.body) == jsonBody
}

func casePipelined() {
	req := "GET /json HTTP/1.1\r\nHost: x\r\n\r\n"
	c, r, err := dial()
	if err != nil {
		result("pipelined-10", false, "dial: %v", err)
		return
	}
	defer c.Close()
	if _, err := c.Write([]byte(strings.Repeat(req, 10))); err != nil {
		result("pipelined-10", false, "write: %v", err)
		return
	}
	for i := 0; i < 10; i++ {
		rs, err := readResp(r, false)
		if err != nil || rs.status != 200 || string(rs.body) != jsonBody {
			result("pipelined-10", false, "response %d: %v %+v", i, err, rs)
			return
		}
	}
	// A mixed pipeline: GET, POST with body, HEAD, GET; framing must survive.
	mixed := req + "POST /echo HTTP/1.1\r\nHost: x\r\nContent-Length: 5\r\n\r\nhello" +
		"HEAD /json HTTP/1.1\r\nHost: x\r\n\r\n" + req
	if _, err := c.Write([]byte(mixed)); err != nil {
		result("pipelined-10", false, "write mixed: %v", err)
		return
	}
	heads := []bool{false, false, true, false}
	for i, h := range heads {
		rs, err := readResp(r, h)
		if err != nil || rs.status != 200 {
			result("pipelined-mixed", false, "response %d: %v %+v", i, err, rs)
			return
		}
		if i == 1 {
			e, err := echoOf(rs)
			if err != nil || e.Length != 5 {
				result("pipelined-mixed", false, "echo length %v %+v", err, e)
				return
			}
		}
	}
	result("pipelined-10", true, "10 responses in order")
	result("pipelined-mixed", true, "GET,POST,HEAD,GET framed correctly")
}

func caseSlowBytes() {
	req := []byte("GET /echo?name=slow HTTP/1.1\r\nHost: x\r\nUser-Agent: drip\r\n\r\n")
	c, r, err := dial()
	if err != nil {
		result("slow-1-byte-writes", false, "dial: %v", err)
		return
	}
	defer c.Close()
	for i := range req {
		if _, err := c.Write(req[i : i+1]); err != nil {
			result("slow-1-byte-writes", false, "write byte %d: %v", i, err)
			return
		}
		time.Sleep(2 * time.Millisecond)
	}
	rs, err := readResp(r, false)
	if err != nil || rs.status != 200 {
		result("slow-1-byte-writes", false, "%v %+v", err, rs)
		return
	}
	e, _ := echoOf(rs)
	result("slow-1-byte-writes", e.Name == "slow" && e.Agent == "drip", "%d writes, echo %+v", len(req), e)
	// Slow body too: header complete, body trickles in.
	body := "0123456789"
	req2 := "POST /echo HTTP/1.1\r\nHost: x\r\nContent-Length: 10\r\n\r\n"
	c.Write([]byte(req2))
	for i := range body {
		c.Write([]byte(body[i : i+1]))
		time.Sleep(2 * time.Millisecond)
	}
	rs, err = readResp(r, false)
	if err != nil || rs.status != 200 {
		result("slow-body-bytes", false, "%v %+v", err, rs)
		return
	}
	e, _ = echoOf(rs)
	result("slow-body-bytes", e.Length == 10, "echo %+v", e)
}

func caseBigHeaders() {
	pad := strings.Repeat("x", 9000)
	raw := "GET /echo HTTP/1.1\r\nHost: x\r\nX-Pad: " + pad + "\r\nUser-Agent: big\r\n\r\n"
	rs, c, _, err := roundTrip(raw, false)
	if err != nil || rs.status != 200 {
		result("headers-9KB", false, "%v %+v", err, rs)
	} else {
		e, _ := echoOf(rs)
		result("headers-9KB", e.Agent == "big", "200, agent after 9KB header = %q", e.Agent)
		c.Close()
	}
	// 40 headers of 1KB each (~40KB) must also pass.
	var sb strings.Builder
	sb.WriteString("GET /echo HTTP/1.1\r\nHost: x\r\n")
	for i := 0; i < 40; i++ {
		fmt.Fprintf(&sb, "X-H%d: %s\r\n", i, strings.Repeat("y", 1000))
	}
	sb.WriteString("User-Agent: many\r\n\r\n")
	rs, c, _, err = roundTrip(sb.String(), false)
	if err != nil || rs.status != 200 {
		result("headers-40x1KB", false, "%v %+v", err, rs)
	} else {
		e, _ := echoOf(rs)
		result("headers-40x1KB", e.Agent == "many", "200, agent = %q", e.Agent)
		c.Close()
	}
	// Headers past 64KB with no end: expect 431 or a close, never a hang.
	raw = "GET / HTTP/1.1\r\nHost: x\r\nX-Pad: " + strings.Repeat("z", 70000) + "\r\n"
	cc, r, err := dial()
	if err != nil {
		result("headers-70KB-unterminated", false, "dial: %v", err)
		return
	}
	defer cc.Close()
	cc.Write([]byte(raw))
	cc.SetReadDeadline(time.Now().Add(3 * time.Second))
	rs, err = readResp(r, false)
	if err == nil {
		closed, _ := closedSoon(cc, r, time.Second)
		result("headers-70KB-unterminated", rs.status == 431 && closed, "status %d closed=%v", rs.status, closed)
	} else {
		result("headers-70KB-unterminated", err == io.EOF || isReset(err), "no response, err=%v", err)
	}
}

func caseLongRequestLine() {
	raw := "GET /" + strings.Repeat("a", 70000) + " HTTP/1.1\r\nHost: x\r\n\r\n"
	c, r, err := dial()
	if err != nil {
		result("request-line-70KB", false, "dial: %v", err)
		return
	}
	defer c.Close()
	c.Write([]byte(raw))
	c.SetReadDeadline(time.Now().Add(3 * time.Second))
	rs, err := readResp(r, false)
	if err == nil {
		closed, why := closedSoon(c, r, time.Second)
		result("request-line-70KB", rs.status == 414 && closed, "status %d, %s", rs.status, why)
		return
	}
	result("request-line-70KB", err == io.EOF || isReset(err), "no response, err=%v", err)
}

func caseBodies() {
	for _, n := range []int{0, 1, 65536, 5 * 1024 * 1024} {
		name := fmt.Sprintf("post-body-%d", n)
		body := bytes.Repeat([]byte("b"), n)
		c, r, err := dial()
		if err != nil {
			result(name, false, "dial: %v", err)
			continue
		}
		hdr := fmt.Sprintf("POST /echo HTTP/1.1\r\nHost: x\r\nContent-Length: %d\r\n\r\n", n)
		if _, err := c.Write(append([]byte(hdr), body...)); err != nil {
			result(name, false, "write: %v", err)
			c.Close()
			continue
		}
		rs, err := readResp(r, false)
		if err != nil || rs.status != 200 {
			result(name, false, "%v %+v", err, rs)
			c.Close()
			continue
		}
		e, jerr := echoOf(rs)
		// The connection must still be usable afterwards (no leftover body bytes).
		c.Write([]byte("GET /json HTTP/1.1\r\nHost: x\r\n\r\n"))
		rs2, err2 := readResp(r, false)
		ok := jerr == nil && e.Length == n && err2 == nil && rs2.status == 200 && string(rs2.body) == jsonBody
		result(name, ok, "echo length %d, follow-up %v", e.Length, err2)
		c.Close()
	}
}

func caseChunked() {
	raw := "POST /echo HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n0\r\n\r\n"
	rs, c, r, err := roundTrip(raw, false)
	if err != nil {
		result("transfer-encoding-chunked", false, "%v", err)
		return
	}
	defer c.Close()
	closed, why := closedSoon(c, r, time.Second)
	result("transfer-encoding-chunked", rs.status == 501 && closed, "status %d, %s", rs.status, why)
}

func caseHTTP10() {
	rs, c, r, err := roundTrip("GET /json HTTP/1.0\r\nHost: x\r\n\r\n", false)
	if err != nil {
		result("http10-closes", false, "%v", err)
		return
	}
	closed, why := closedSoon(c, r, time.Second)
	result("http10-closes", rs.status == 200 && closed, "status %d, %s", rs.status, why)
	c.Close()
	// HTTP/1.0 with keep-alive stays open for a second request.
	req := "GET /json HTTP/1.0\r\nHost: x\r\nConnection: keep-alive\r\n\r\n"
	rs, c, r, err = roundTrip(req, false)
	if err != nil || rs.status != 200 {
		result("http10-keepalive", false, "%v %+v", err, rs)
		return
	}
	defer c.Close()
	c.Write([]byte(req))
	rs2, err := readResp(r, false)
	result("http10-keepalive", err == nil && rs2.status == 200, "second response err=%v", err)
}

func caseConnectionClose() {
	rs, c, r, err := roundTrip("GET /json HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n", false)
	if err != nil {
		result("http11-connection-close", false, "%v", err)
		return
	}
	defer c.Close()
	closed, why := closedSoon(c, r, time.Second)
	result("http11-connection-close", rs.status == 200 && closed, "status %d, %s", rs.status, why)
}

func caseHEAD() {
	rs, c, r, err := roundTrip("HEAD /json HTTP/1.1\r\nHost: x\r\n\r\n", true)
	if err != nil {
		result("head-no-body", false, "%v", err)
		return
	}
	defer c.Close()
	cl := rs.headers["content-length"]
	// A GET right after on the same connection proves no body bytes were sent for HEAD.
	c.Write([]byte("GET /json HTTP/1.1\r\nHost: x\r\n\r\n"))
	rs2, err := readResp(r, false)
	ok := rs.status == 200 && cl == strconv.Itoa(len(jsonBody)) && err == nil && rs2.status == 200 && string(rs2.body) == jsonBody
	result("head-no-body", ok, "status %d, Content-Length %s, follow-up GET err=%v", rs.status, cl, err)
}

func caseMalformed() {
	cases := []struct{ name, raw string }{
		{"garbage", "GARBAGE\r\nHost: x\r\n\r\n"},
		{"no-version", "GET /json\r\nHost: x\r\n\r\n"},
		{"leading-space", " GET /json HTTP/1.1\r\n\r\n"},
		{"double-space", "GET  /json HTTP/1.1\r\n\r\n"},
		{"not-http", "GET /json XTTP/1.1\r\n\r\n"},
		{"empty-method", " /json HTTP/1.1\r\n\r\n"},
		{"binary", "\x16\x03\x01\x00\xa5\x01\x00\x00\xa1\x03\x03\r\n\r\n"},
	}
	allOK := true
	var notes []string
	for _, tc := range cases {
		rs, c, r, err := roundTrip(tc.raw, false)
		if err != nil {
			allOK = false
			notes = append(notes, tc.name+": "+err.Error())
			continue
		}
		closed, _ := closedSoon(c, r, 500*time.Millisecond)
		c.Close()
		if rs.status != 400 || !closed {
			allOK = false
			notes = append(notes, fmt.Sprintf("%s: status %d closed=%v", tc.name, rs.status, closed))
		}
	}
	result("malformed-request-line", allOK, "%d variants -> 400+close %s", len(cases), strings.Join(notes, "; "))
	// Bad Content-Length values must be rejected, not silently parsed.
	badCL := []string{"abc", "-1", "1x2", "99999999999999999999"}
	allOK = true
	notes = nil
	for _, v := range badCL {
		raw := "POST /echo HTTP/1.1\r\nHost: x\r\nContent-Length: " + v + "\r\n\r\n"
		c, r, err := dial()
		if err != nil {
			allOK = false
			continue
		}
		c.Write([]byte(raw))
		c.SetReadDeadline(time.Now().Add(2 * time.Second))
		rs, err := readResp(r, false)
		if err != nil {
			if !(err == io.EOF || isReset(err)) {
				allOK = false
				notes = append(notes, fmt.Sprintf("%q: %v", v, err))
			}
		} else if rs.status != 400 && rs.status != 413 {
			allOK = false
			notes = append(notes, fmt.Sprintf("%q: status %d", v, rs.status))
		}
		c.Close()
	}
	result("bad-content-length", allOK, "%d variants -> 400/413/close %s", len(badCL), strings.Join(notes, "; "))
}

// caseDuplicateCL checks that conflicting Content-Length headers are rejected and the
// connection closed before any later pipelined request runs, while identical ones are fine.
func caseDuplicateCL() {
	follow := "GET /json HTTP/1.1\r\nHost: x\r\n\r\n"
	allOK := true
	var notes []string
	for _, pair := range [][2]string{{"5", "0"}, {"0", "5"}, {"3", "4"}} {
		raw := "POST /echo HTTP/1.1\r\nHost: x\r\nContent-Length: " + pair[0] + "\r\nContent-Length: " + pair[1] + "\r\n\r\nhello" + follow
		rs, c, r, err := roundTrip(raw, false)
		if err != nil {
			if !(err == io.EOF || isReset(err)) {
				allOK = false
				notes = append(notes, fmt.Sprintf("%s,%s: %v", pair[0], pair[1], err))
			}
			continue
		}
		closed, why := closedSoon(c, r, time.Second)
		c.Close()
		if rs.status != 400 || !closed {
			allOK = false
			notes = append(notes, fmt.Sprintf("%s,%s: status %d %s", pair[0], pair[1], rs.status, why))
		}
	}
	raw := "POST /echo HTTP/1.1\r\nHost: x\r\nContent-Length: 5\r\nContent-Length: 5\r\n\r\nhello" + follow
	rs, c, r, err := roundTrip(raw, false)
	if err != nil {
		allOK = false
		notes = append(notes, "identical: "+err.Error())
	} else {
		rs2, err2 := readResp(r, false)
		c.Close()
		if rs.status != 200 || err2 != nil || rs2.status != 200 {
			allOK = false
			notes = append(notes, fmt.Sprintf("identical: status %d, follow-up %v", rs.status, err2))
		}
	}
	result("duplicate-content-length", allOK, "conflicting -> 400+close, identical accepted %s", strings.Join(notes, "; "))
}

// caseFieldLines checks that a header line that is not "token: value" is rejected and the
// connection closed before a pipelined follow-up runs (RFC 9112 5.1, 5.2): a parser that
// trims, unfolds or skips the line would frame the request differently.
func caseFieldLines() {
	follow := "GET /json HTTP/1.1\r\nHost: x\r\n\r\n"
	cases := []struct{ name, line, body string }{
		{"space-before-colon", "Content-Length : 5", "hello"},
		{"tab-before-colon", "Content-Length\t: 5", "hello"},
		{"te-space-before-colon", "Transfer-Encoding : chunked", "5\r\nhello\r\n0\r\n\r\n"},
		{"obs-fold", "X-A: 1\r\n Content-Length: 5", "hello"},
		{"no-colon", "Content-Length 5", "hello"},
		{"empty-name", ": 5", "hello"},
		{"space-in-name", "Content Length: 5", "hello"},
		{"control-in-name", "Content-Length\x0b: 5", "hello"},
	}
	allOK := true
	var notes []string
	for _, tc := range cases {
		raw := "POST /echo HTTP/1.1\r\nHost: x\r\n" + tc.line + "\r\n\r\n" + tc.body + follow
		rs, c, r, err := roundTrip(raw, false)
		if err != nil {
			if !(err == io.EOF || isReset(err)) {
				allOK = false
				notes = append(notes, tc.name+": "+err.Error())
			}
			continue
		}
		closed, why := closedSoon(c, r, time.Second)
		c.Close()
		if rs.status != 400 || !closed {
			allOK = false
			notes = append(notes, fmt.Sprintf("%s: status %d %s", tc.name, rs.status, why))
		}
	}
	// Every token character may appear in a name, and the space after the colon is optional.
	raw := "POST /echo HTTP/1.1\r\nHost:x\r\nX-Tchar!#$%&'*+-.^_`|~09AZaz: v\r\nContent-Length:5\r\n\r\nhello" + follow
	rs, c, r, err := roundTrip(raw, false)
	if err != nil {
		allOK = false
		notes = append(notes, "valid: "+err.Error())
	} else {
		e, jerr := echoOf(rs)
		rs2, err2 := readResp(r, false)
		c.Close()
		if rs.status != 200 || jerr != nil || e.Length != 5 || err2 != nil || rs2.status != 200 {
			allOK = false
			notes = append(notes, fmt.Sprintf("valid: status %d, length %d, follow-up %v", rs.status, e.Length, err2))
		}
	}
	result("header-field-lines", allOK, "%d malformed -> 400+close, tokens accepted %s", len(cases), strings.Join(notes, "; "))
}

func caseClientCloseMid() {
	partials := []string{
		"GET /js",
		"GET /json HTTP/1.1\r\nHost: x\r\nUser-Ag",
		"POST /echo HTTP/1.1\r\nHost: x\r\nContent-Length: 1000\r\n\r\nabc",
		"POST /echo HTTP/1.1\r\nHost: x\r\nContent-Length: 5000000\r\n\r\n" + strings.Repeat("q", 300000),
	}
	for i, p := range partials {
		c, err := net.DialTimeout("tcp", addr, 5*time.Second)
		if err != nil {
			result("client-close-mid-request", false, "dial %d: %v", i, err)
			return
		}
		c.Write([]byte(p))
		time.Sleep(20 * time.Millisecond)
		c.Close()
	}
	// Also an abrupt reset mid-body.
	c, err := net.DialTimeout("tcp", addr, 5*time.Second)
	if err == nil {
		c.Write([]byte("POST /echo HTTP/1.1\r\nHost: x\r\nContent-Length: 100000\r\n\r\n" + strings.Repeat("r", 1000)))
		c.(*net.TCPConn).SetLinger(0)
		time.Sleep(20 * time.Millisecond)
		c.Close()
	}
	time.Sleep(50 * time.Millisecond)
	result("client-close-mid-request", alive(), "%d partial closes + 1 reset, server alive", len(partials))
}

func raiseFDLimit() {
	var rl syscall.Rlimit
	if err := syscall.Getrlimit(syscall.RLIMIT_NOFILE, &rl); err != nil {
		return
	}
	rl.Cur = rl.Max
	if rl.Cur > 60000 {
		rl.Cur = 60000
	}
	syscall.Setrlimit(syscall.RLIMIT_NOFILE, &rl)
}

func caseManyConns(n int) {
	name := fmt.Sprintf("%d-conns-idle-reuse", n)
	conns := make([]net.Conn, n)
	readers := make([]*bufio.Reader, n)
	var dialFail, firstFail, idleFail atomic.Int64
	var firstErr atomic.Value
	var wg sync.WaitGroup
	req := []byte("GET /json HTTP/1.1\r\nHost: x\r\n\r\n")
	for i := 0; i < n; i++ {
		if i%100 == 99 {
			time.Sleep(15 * time.Millisecond)
		}
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			c, err := net.DialTimeout("tcp", addr, 10*time.Second)
			if err != nil {
				dialFail.Add(1)
				firstErr.CompareAndSwap(nil, err.Error())
				return
			}
			c.SetDeadline(time.Now().Add(30 * time.Second))
			conns[i] = c
			readers[i] = bufio.NewReaderSize(c, 4096)
			c.Write(req)
			rs, err := readResp(readers[i], false)
			if err != nil || rs.status != 200 {
				firstFail.Add(1)
				firstErr.CompareAndSwap(nil, fmt.Sprint(err))
			}
		}(i)
	}
	wg.Wait()
	// Idle, then prove every connection is still served (nothing got dropped while idle).
	time.Sleep(2 * time.Second)
	for i := 0; i < n; i++ {
		if conns[i] == nil {
			continue
		}
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			conns[i].SetDeadline(time.Now().Add(30 * time.Second))
			conns[i].Write(req)
			rs, err := readResp(readers[i], false)
			if err != nil || rs.status != 200 || string(rs.body) != jsonBody {
				idleFail.Add(1)
				firstErr.CompareAndSwap(nil, fmt.Sprint(err))
			}
		}(i)
	}
	wg.Wait()
	for _, c := range conns {
		if c != nil {
			c.Close()
		}
	}
	ok := dialFail.Load() == 0 && firstFail.Load() == 0 && idleFail.Load() == 0
	result(name, ok, "dial-fail %d first-fail %d after-idle-fail %d %v", dialFail.Load(), firstFail.Load(), idleFail.Load(), firstErr.Load())
}

func caseResetsUnderLoad() {
	stop := make(chan struct{})
	var good, goodErr, resets atomic.Int64
	var firstErr atomic.Value
	var wg sync.WaitGroup
	req := []byte("GET /json HTTP/1.1\r\nHost: x\r\n\r\n")
	for g := 0; g < 16; g++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for {
				select {
				case <-stop:
					return
				default:
				}
				c, err := net.DialTimeout("tcp", addr, 5*time.Second)
				if err != nil {
					goodErr.Add(1)
					firstErr.CompareAndSwap(nil, err.Error())
					continue
				}
				r := bufio.NewReaderSize(c, 4096)
				for k := 0; k < 200; k++ {
					c.SetDeadline(time.Now().Add(5 * time.Second))
					if _, err := c.Write(req); err != nil {
						goodErr.Add(1)
						firstErr.CompareAndSwap(nil, err.Error())
						break
					}
					rs, err := readResp(r, false)
					if err != nil || rs.status != 200 {
						goodErr.Add(1)
						firstErr.CompareAndSwap(nil, fmt.Sprint(err))
						break
					}
					good.Add(1)
				}
				c.Close()
			}
		}()
	}
	for g := 0; g < 16; g++ {
		wg.Add(1)
		go func(g int) {
			defer wg.Done()
			for {
				select {
				case <-stop:
					return
				default:
				}
				c, err := net.DialTimeout("tcp", addr, 5*time.Second)
				if err != nil {
					continue
				}
				tc := c.(*net.TCPConn)
				tc.SetLinger(0)
				switch g % 4 {
				case 0: // reset with nothing sent
				case 1: // reset after a partial request
					c.Write([]byte("GET /json HTTP/1.1\r\nHos"))
				case 2: // reset after a full request, before reading the response
					c.Write(req)
				case 3: // reset after 10 pipelined requests
					c.Write(bytes.Repeat(req, 10))
				}
				c.Close()
				resets.Add(1)
			}
		}(g)
	}
	time.Sleep(3 * time.Second)
	close(stop)
	wg.Wait()
	time.Sleep(100 * time.Millisecond)
	ok := goodErr.Load() == 0 && alive()
	result("resets-under-load", ok, "%d good requests, %d good errors, %d resets, alive=%v %v", good.Load(), goodErr.Load(), resets.Load(), alive(), firstErr.Load())
}

func caseQueryDecoding() {
	cases := []struct{ query, name, rawQuery string }{
		{"name=a%20b+c", "a b c", "name=a%20b+c"},
		{"name=%E2%9C%93", "✓", "name=%E2%9C%93"},
		{"name=%zz%4", "%zz%4", "name=%zz%4"},
		{"name=", "", "name="},
		{"name", "", "name"},
		{"other=1&name=last&x=2", "last", "other=1&name=last&x=2"},
		{"xname=1&name=2", "2", "xname=1&name=2"},
		{"name=a%3D%26b", "a=&b", "name=a%3D%26b"},
		{"name=%2", "%2", "name=%2"},
		{"name=%41%42", "AB", "name=%41%42"},
		{"", "", ""},
	}
	allOK := true
	var notes []string
	for _, tc := range cases {
		path := "/echo"
		if tc.query != "" {
			path += "?" + tc.query
		}
		rs, err := get(path)
		if err != nil || rs.status != 200 {
			allOK = false
			notes = append(notes, fmt.Sprintf("%q: %v", tc.query, err))
			continue
		}
		e, err := echoOf(rs)
		if err != nil || e.Name != tc.name || e.Query != tc.rawQuery || e.Path != "/echo" {
			allOK = false
			notes = append(notes, fmt.Sprintf("%q: got name=%q query=%q path=%q err=%v", tc.query, e.Name, e.Query, e.Path, err))
		}
	}
	result("query-param-decoding", allOK, "%d cases %s", len(cases), strings.Join(notes, "; "))
}

func rssKB(pid int) int {
	out, err := exec.Command("ps", "-o", "rss=", "-p", strconv.Itoa(pid)).Output()
	if err != nil {
		return -1
	}
	n, _ := strconv.Atoi(strings.TrimSpace(string(out)))
	return n
}

// load sends total pipelined GET /json requests over conns connections, pipe at a time.
func load(conns, pipe int, total int64) (int64, int64) {
	var done, errs atomic.Int64
	var wg sync.WaitGroup
	req := bytes.Repeat([]byte("GET /json HTTP/1.1\r\nHost: x\r\n\r\n"), pipe)
	for i := 0; i < conns; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			c, err := net.DialTimeout("tcp", addr, 5*time.Second)
			if err != nil {
				errs.Add(1)
				return
			}
			defer c.Close()
			r := bufio.NewReaderSize(c, 1<<16)
			for done.Load() < total {
				c.SetDeadline(time.Now().Add(10 * time.Second))
				if _, err := c.Write(req); err != nil {
					errs.Add(1)
					return
				}
				for k := 0; k < pipe; k++ {
					rs, err := readResp(r, false)
					if err != nil || rs.status != 200 {
						errs.Add(1)
						return
					}
				}
				done.Add(int64(pipe))
			}
		}()
	}
	wg.Wait()
	return done.Load(), errs.Load()
}

func caseRSS(pid int, total int64) {
	if pid <= 0 {
		result("rss-flat-2M", false, "no server pid (pass -pid)")
		return
	}
	load(50, 20, 100000) // warm up buffers first
	before := rssKB(pid)
	t0 := time.Now()
	mid := int64(0)
	var midRSS int
	done, errs := load(50, 20, total/2)
	midRSS = rssKB(pid)
	mid = done
	done2, errs2 := load(50, 20, total-total/2)
	el := time.Since(t0)
	after := rssKB(pid)
	growth := after - before
	ok := errs+errs2 == 0 && before > 0 && growth <= before/10+2048
	result("rss-flat-2M", ok, "rss KB before %d mid %d after %d (growth %d KB) over %d reqs in %s (%.0f req/s), errors %d",
		before, midRSS, after, growth, mid+done2, el.Round(time.Millisecond), float64(mid+done2)/el.Seconds(), errs+errs2)
}

// caseLargeResponse asks /echo to reflect a 60KB query, 5 times pipelined, so the ~600KB of
// output exceeds the socket buffer and exercises the pending-output (partial write) path.
func caseLargeResponse() {
	big := strings.Repeat("Q", 60000)
	req := "GET /echo?name=" + big + " HTTP/1.1\r\nHost: x\r\n\r\n"
	c, r, err := dial()
	if err != nil {
		result("large-response-pipelined", false, "dial: %v", err)
		return
	}
	defer c.Close()
	go c.Write([]byte(strings.Repeat(req, 5)))
	for i := 0; i < 5; i++ {
		rs, err := readResp(r, false)
		if err != nil || rs.status != 200 {
			result("large-response-pipelined", false, "response %d: %v", i, err)
			return
		}
		e, err := echoOf(rs)
		if err != nil || e.Name != big || e.Query != "name="+big {
			result("large-response-pipelined", false, "response %d: bad echo (name len %d) %v", i, len(e.Name), err)
			return
		}
	}
	// HXYZ must not be treated as HEAD: the handler sees the method and the body is sent.
	c.Write([]byte("HXYZ /plaintext HTTP/1.1\r\nHost: x\r\n\r\n"))
	rs, err := readResp(r, false)
	ok := err == nil && string(rs.body) == "Hello, World!"
	result("large-response-pipelined", ok, "5 x 120KB responses, HXYZ body err=%v", err)
}

// caseNoReadBackpressure pipelines 300k requests without reading for 2s: the server must
// stop reading instead of buffering every response, then deliver all of them once we read.
func caseNoReadBackpressure(pid int) {
	if pid <= 0 {
		result("pipelined-no-read-backpressure", false, "no server pid")
		return
	}
	c, r, err := dial()
	if err != nil {
		result("pipelined-no-read-backpressure", false, "dial: %v", err)
		return
	}
	defer c.Close()
	c.SetDeadline(time.Now().Add(60 * time.Second))
	batch := bytes.Repeat([]byte("GET /json HTTP/1.1\r\nHost: x\r\n\r\n"), 100)
	before := rssKB(pid)
	var written atomic.Int64
	var werr atomic.Value
	done := make(chan struct{})
	go func() {
		defer close(done)
		for i := 0; i < 3000; i++ {
			if _, err := c.Write(batch); err != nil {
				werr.Store(err.Error())
				return
			}
			written.Add(100)
		}
	}()
	time.Sleep(2 * time.Second)
	mid := rssKB(pid)
	stalled := written.Load()
	count := int64(0)
	for {
		rs, err := readResp(r, false)
		if err != nil || rs.status != 200 || string(rs.body) != jsonBody {
			result("pipelined-no-read-backpressure", false, "response %d: %v %+v (written %d)", count, err, rs, written.Load())
			return
		}
		count++
		select {
		case <-done:
			if count == written.Load() {
				growth := mid - before
				ok := werr.Load() == nil && growth < 8192
				result("pipelined-no-read-backpressure", ok, "server accepted %d reqs while unread (rss %d -> %d KB, +%d KB), all %d responses delivered %v",
					stalled, before, mid, growth, count, werr.Load())
				return
			}
		default:
		}
	}
}

func findPID(port string) int {
	out, err := exec.Command("lsof", "-ti", "tcp:"+port, "-sTCP:LISTEN").Output()
	if err != nil {
		return 0
	}
	f := strings.Fields(string(out))
	if len(f) == 0 {
		return 0
	}
	n, _ := strconv.Atoi(f[0])
	return n
}

func main() {
	flag.StringVar(&addr, "addr", "127.0.0.1:9200", "server host:port")
	pid := flag.Int("pid", 0, "server pid for RSS checks (default: lsof on the port)")
	heavy := flag.Bool("heavy", true, "run the 5000-connection, reset-storm and RSS cases")
	nconn := flag.Int("conns", 5000, "connections for the many-connections case")
	reqs := flag.Int64("reqs", 2000000, "requests for the RSS case")
	only := flag.String("only", "", "run only the case whose name contains this")
	flag.Parse()
	raiseFDLimit()
	if *pid == 0 {
		_, port, _ := net.SplitHostPort(addr)
		*pid = findPID(port)
	}
	if !alive() {
		fmt.Println("server at", addr, "does not answer GET /json")
		os.Exit(2)
	}
	cases := []struct {
		name string
		fn   func()
	}{
		{"pipelined", casePipelined},
		{"slow", caseSlowBytes},
		{"headers", caseBigHeaders},
		{"request-line", caseLongRequestLine},
		{"bodies", caseBodies},
		{"chunked", caseChunked},
		{"http10", caseHTTP10},
		{"connection-close", caseConnectionClose},
		{"head", caseHEAD},
		{"malformed", caseMalformed},
		{"duplicate-cl", caseDuplicateCL},
		{"field-lines", caseFieldLines},
		{"client-close", caseClientCloseMid},
		{"query", caseQueryDecoding},
		{"large-response", caseLargeResponse},
	}
	if *heavy {
		cases = append(cases,
			struct {
				name string
				fn   func()
			}{"backpressure", func() { caseNoReadBackpressure(*pid) }},
			struct {
				name string
				fn   func()
			}{"many-conns", func() { caseManyConns(*nconn) }},
			struct {
				name string
				fn   func()
			}{"resets", caseResetsUnderLoad},
			struct {
				name string
				fn   func()
			}{"rss", func() { caseRSS(*pid, *reqs) }},
		)
	}
	for _, c := range cases {
		if *only != "" && !strings.Contains(c.name, *only) {
			continue
		}
		c.fn()
		if !alive() {
			fmt.Println("FAIL server died after case", c.name)
			os.Exit(1)
		}
	}
	fmt.Printf("\n%d passed, %d failed\n", passed, failed)
	if failed > 0 {
		os.Exit(1)
	}
}
