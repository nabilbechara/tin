// The fasthttp baseline: the same /json and /plaintext endpoints as examples/api.tin.
package main

import (
	"encoding/json"
	"os"

	"github.com/valyala/fasthttp"
)

type Message struct {
	Message string `json:"message"`
}

func main() {
	addr := ":9182"
	if len(os.Args) > 1 {
		addr = os.Args[1]
	}
	h := func(ctx *fasthttp.RequestCtx) {
		switch string(ctx.Path()) {
		case "/json":
			ctx.SetContentType("application/json")
			b, _ := json.Marshal(Message{Message: "Hello, World!"})
			ctx.Write(b)
		case "/plaintext":
			ctx.SetContentType("text/plain; charset=utf-8")
			ctx.WriteString("Hello, World!")
		default:
			ctx.SetStatusCode(404)
		}
	}
	s := &fasthttp.Server{Handler: h, Name: "fasthttp"}
	s.ListenAndServe(addr)
}
