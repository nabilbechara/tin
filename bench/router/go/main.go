// The routers of bench/router/router.tin with chi: Find is the lookup alone (a reused
// routing context), ServeHTTP a request through the router (one parsed request reused, a
// writer that discards, the handler). go run . in bench/router/go.
package main

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"time"

	"github.com/go-chi/chi/v5"
)

func h(w http.ResponseWriter, r *http.Request) {
	w.Write([]byte("ok"))
}

// build makes a router of n routes, as in router.tin.
func build(n int) *chi.Mux {
	r := chi.NewRouter()
	if n == 1 {
		r.Get("/res0/{id}", h)
		return r
	}
	per := 2
	if n > 20 {
		per = 4
	}
	for i := 0; i*per < n; i++ {
		r.Get(fmt.Sprintf("/res%d", i), h)
		r.Get(fmt.Sprintf("/res%d/{id}", i), h)
		if per == 4 {
			r.Put(fmt.Sprintf("/res%d/{id}", i), h)
			r.Get(fmt.Sprintf("/res%d/{id}/items", i), h)
		}
	}
	return r
}

func match(label string, r *chi.Mux, method, path, want string) {
	rctx := chi.NewRouteContext()
	if got := r.Find(rctx, method, path); got != want {
		fmt.Println("wrong match for", path, got)
		return
	}
	n := 5000000
	t0 := time.Now()
	for i := 0; i < n; i++ {
		rctx.Reset()
		r.Find(rctx, method, path)
	}
	fmt.Printf("%-34s %6.1f ns\n", label, float64(time.Since(t0).Nanoseconds())/float64(n))
}

// discard is a ResponseWriter that keeps nothing, so run measures chi rather than a recorder.
type discard struct{ h http.Header }

func (d *discard) Header() http.Header         { return d.h }
func (d *discard) Write(b []byte) (int, error) { return len(b), nil }
func (d *discard) WriteHeader(int)             {}

func run(label string, r *chi.Mux, method, path string) {
	n := 200000
	best := 0.0
	req := httptest.NewRequest(method, path, nil)
	w := &discard{h: http.Header{}}
	for round := 0; round < 5; round++ {
		t0 := time.Now()
		for i := 0; i < n; i++ {
			r.ServeHTTP(w, req)
		}
		ns := float64(time.Since(t0).Nanoseconds()) / float64(n)
		if round == 0 || ns < best {
			best = ns
		}
	}
	fmt.Printf("%-34s %6.1f ns\n", label, best)
}

func main() {
	r1, r20, r200 := build(1), build(20), build(200)
	match("match 1   /res0/42", r1, "GET", "/res0/42", "/res0/{id}")
	match("match 20  /res7 (static)", r20, "GET", "/res7", "/res7")
	match("match 20  /res7/42", r20, "GET", "/res7/42", "/res7/{id}")
	match("match 20  /nope (404)", r20, "GET", "/nope", "")
	match("match 200 /res37 (static)", r200, "GET", "/res37", "/res37")
	match("match 200 /res37/42", r200, "GET", "/res37/42", "/res37/{id}")
	match("match 200 PUT /res37/42", r200, "PUT", "/res37/42", "/res37/{id}")
	match("match 200 /res37/42/items", r200, "GET", "/res37/42/items", "/res37/{id}/items")
	match("match 200 /nope (404)", r200, "GET", "/nope", "")
	run("run 1   /res0/42", r1, "GET", "/res0/42")
	run("run 20  /res7/42", r20, "GET", "/res7/42")
	run("run 200 /res37/42/items", r200, "GET", "/res37/42/items")
	run("run 200 /nope (404)", r200, "GET", "/nope")
}
