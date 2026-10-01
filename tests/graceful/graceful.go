// graceful.go checks anvil's graceful shutdown: start a server binary, hold connections in
// various states, send SIGTERM and verify that in-flight requests complete (with
// "Connection: close"), that the listener closes, and that the process exits 0 in time.
//
//	go run tests/graceful/graceful.go bin/api 9381          (macOS)
//	GOOS=linux GOARCH=arm64 go build -o bin/linux/graceful tests/graceful/graceful.go
//	docker run --rm -v $PWD/bin/linux:/w tin-debian-arm64 /w/graceful /w/api 9381
package main

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"syscall"
	"time"
)

var failures int

func check(ok bool, format string, args ...any) {
	if ok {
		fmt.Printf("ok   "+format+"\n", args...)
	} else {
		fmt.Printf("FAIL "+format+"\n", args...)
		failures++
	}
}

type server struct {
	cmd  *exec.Cmd
	addr string
	done chan error
	t0   time.Time
}

func start(bin string, port int, grace string) *server {
	cmd := exec.Command(bin)
	cmd.Env = append(os.Environ(), "TIN_CORES=2", "PORT="+strconv.Itoa(port), "TIN_GRACE="+grace)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Start(); err != nil {
		fmt.Println("cannot start", bin, err)
		os.Exit(2)
	}
	s := &server{cmd: cmd, addr: "127.0.0.1:" + strconv.Itoa(port), done: make(chan error, 1)}
	go func() { s.done <- cmd.Wait() }()
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		c, err := net.DialTimeout("tcp", s.addr, 200*time.Millisecond)
		if err == nil {
			c.Close()
			return s
		}
		time.Sleep(20 * time.Millisecond)
	}
	fmt.Println("server never became ready")
	os.Exit(2)
	return nil
}

// term sends SIGTERM and records the moment.
func (s *server) term() {
	s.t0 = time.Now()
	s.cmd.Process.Signal(syscall.SIGTERM)
}

// exited waits up to limit for the process and returns (exited, code, elapsed since term).
func (s *server) exited(limit time.Duration) (bool, int, time.Duration) {
	select {
	case err := <-s.done:
		code := 0
		var ee *exec.ExitError
		if errors.As(err, &ee) {
			code = ee.ExitCode()
		} else if err != nil {
			code = -1
		}
		return true, code, time.Since(s.t0)
	case <-time.After(limit):
		return false, -1, time.Since(s.t0)
	}
}

func (s *server) kill() {
	s.cmd.Process.Kill()
	<-s.done
}

// readResponse reads one HTTP/1.1 response and reports status, the Connection header and body.
func readResponse(r *bufio.Reader) (status int, connection string, body string, err error) {
	line, err := r.ReadString('\n')
	if err != nil {
		return 0, "", "", err
	}
	parts := strings.SplitN(line, " ", 3)
	if len(parts) < 2 {
		return 0, "", "", fmt.Errorf("bad status line %q", line)
	}
	status, _ = strconv.Atoi(parts[1])
	length := -1
	for {
		h, err := r.ReadString('\n')
		if err != nil {
			return status, connection, "", err
		}
		h = strings.TrimRight(h, "\r\n")
		if h == "" {
			break
		}
		k, v, _ := strings.Cut(h, ":")
		v = strings.TrimSpace(v)
		switch strings.ToLower(k) {
		case "content-length":
			length, _ = strconv.Atoi(v)
		case "connection":
			connection = strings.ToLower(v)
		}
	}
	if length < 0 {
		return status, connection, "", fmt.Errorf("no content-length")
	}
	buf := make([]byte, length)
	_, err = io.ReadFull(r, buf)
	return status, connection, string(buf), err
}

// listenerClosed reports whether a new connection is refused (or at least not served) now.
func listenerClosed(addr string) bool {
	c, err := net.DialTimeout("tcp", addr, 300*time.Millisecond)
	if err != nil {
		return true
	}
	defer c.Close()
	// macOS may complete the handshake from the backlog of a closed listener; a request then gets no answer.
	c.SetDeadline(time.Now().Add(500 * time.Millisecond))
	fmt.Fprintf(c, "GET /healthz HTTP/1.1\r\nHost: x\r\n\r\n")
	_, _, _, err = readResponse(bufio.NewReader(c))
	return err != nil
}

func main() {
	if len(os.Args) < 2 {
		fmt.Println("usage: graceful SERVER_BINARY [PORT]")
		os.Exit(2)
	}
	bin := os.Args[1]
	port := 9381
	if len(os.Args) > 2 {
		port, _ = strconv.Atoi(os.Args[2])
	}

	// A: a slow client is in the middle of sending a request when SIGTERM arrives.
	s := start(bin, port, "25")
	slow, err := net.Dial("tcp", s.addr)
	check(err == nil, "A: connect %v", err)
	fmt.Fprintf(slow, "GET /json HTTP/1.1\r\nHost: x\r\nX-Slow: ")
	time.Sleep(100 * time.Millisecond)
	s.term()
	time.Sleep(300 * time.Millisecond)
	check(listenerClosed(s.addr), "A: listener closed after SIGTERM")
	fmt.Fprintf(slow, "yes\r\n\r\n")
	slow.SetDeadline(time.Now().Add(3 * time.Second))
	st, conn, body, err := readResponse(bufio.NewReader(slow))
	check(err == nil && st == 200 && strings.Contains(body, "Hello, World!"), "A: in-flight request answered: status %d body %q err %v", st, body, err)
	check(conn == "close", "A: response carries Connection: close (got %q)", conn)
	one := make([]byte, 1)
	_, err = slow.Read(one)
	check(err == io.EOF, "A: server closed the connection after the response (read err %v)", err)
	exited, code, took := s.exited(5 * time.Second)
	check(exited && code == 0, "A: process exited 0 within 5s (exited %v code %d after %v)", exited, code, took.Round(time.Millisecond))
	if !exited {
		s.kill()
	}
	slow.Close()

	// B: an idle keep-alive connection sends a request after SIGTERM: served with Connection: close.
	s = start(bin, port, "25")
	idle, _ := net.Dial("tcp", s.addr)
	fmt.Fprintf(idle, "GET /healthz HTTP/1.1\r\nHost: x\r\n\r\n")
	r := bufio.NewReader(idle)
	st, conn, body, err = readResponse(r)
	check(err == nil && st == 200 && body == "ok" && conn == "", "B: request before SIGTERM: status %d body %q conn %q", st, body, conn)
	s.term()
	time.Sleep(300 * time.Millisecond)
	exited, _, _ = s.exited(0)
	check(!exited, "B: process still running while a connection is open")
	fmt.Fprintf(idle, "GET /plaintext HTTP/1.1\r\nHost: x\r\n\r\n")
	idle.SetDeadline(time.Now().Add(3 * time.Second))
	st, conn, body, err = readResponse(r)
	check(err == nil && st == 200 && body == "Hello, World!" && conn == "close", "B: request after SIGTERM served with Connection: close: status %d body %q conn %q err %v", st, body, conn, err)
	_, err = idle.Read(one)
	check(err == io.EOF, "B: connection closed by the server (read err %v)", err)
	exited, code, took = s.exited(5 * time.Second)
	check(exited && code == 0 && took < 3*time.Second, "B: exit 0 promptly once no connection is left (exited %v code %d after %v)", exited, code, took.Round(time.Millisecond))
	if !exited {
		s.kill()
	}
	idle.Close()

	// C: an idle connection that never sends anything: the process exits 0 when TIN_GRACE ends.
	s = start(bin, port, "2")
	hold, _ := net.Dial("tcp", s.addr)
	s.term()
	exited, code, took = s.exited(8 * time.Second)
	check(exited && code == 0 && took >= 1500*time.Millisecond && took < 6*time.Second, "C: exit 0 at the 2s grace deadline with an idle connection open (exited %v code %d after %v)", exited, code, took.Round(time.Millisecond))
	if !exited {
		s.kill()
	}
	hold.Close()

	// D: a second signal while draining exits immediately.
	s = start(bin, port, "30")
	hold2, _ := net.Dial("tcp", s.addr)
	s.term()
	time.Sleep(300 * time.Millisecond)
	s.cmd.Process.Signal(syscall.SIGINT)
	exited, code, took = s.exited(3 * time.Second)
	check(exited && code == 0 && took < 2*time.Second, "D: second signal exits 0 at once (exited %v code %d after %v)", exited, code, took.Round(time.Millisecond))
	if !exited {
		s.kill()
	}
	hold2.Close()

	// E: no connections at all: SIGTERM exits 0 right away.
	s = start(bin, port, "25")
	s.term()
	exited, code, took = s.exited(3 * time.Second)
	check(exited && code == 0 && took < 1500*time.Millisecond, "E: SIGTERM with no connections exits 0 at once (exited %v code %d after %v)", exited, code, took.Round(time.Millisecond))
	if !exited {
		s.kill()
	}

	if failures > 0 {
		fmt.Printf("%d FAILED\n", failures)
		os.Exit(1)
	}
	fmt.Println("graceful shutdown: all checks pass")
}
