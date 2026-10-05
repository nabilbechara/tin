// The Go twin of argo_twin.tin: the same inputs through encoding/json, as the default decoder
// and with DisallowUnknownFields. Output: "<case> default=<ok|fault> strict=<ok|fault>".
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"strings"
)

type T struct {
	N    uint8    `json:"n"`
	Name string   `json:"name"`
	Tags []string `json:"tags"`
}

var cases = []struct{ name, in string }{
	{"unknown", `{"n":1,"zz":2}`},
	{"duplicate", `{"n":1,"n":2}`},
	{"trailing_comma", `{"tags":["a",]}`},
	{"type_mismatch", `{"n":"x"}`},
	{"out_of_range", `{"n":700}`},
	{"trailing_garbage", `{"n":1} x`},
	{"bad_utf8", "{\"name\":\"a\xffb\"}"},
	{"lone_surrogate", `{"name":"\ud800"}`},
	{"valid_pair", `{"name":"😀"}`},
}

func decode(in string, strict bool) string {
	dec := json.NewDecoder(strings.NewReader(in))
	if strict {
		dec.DisallowUnknownFields()
	}
	var v T
	if err := dec.Decode(&v); err != nil {
		return "fault"
	}
	if _, err := dec.Token(); err != io.EOF {
		return "fault"
	}
	return "ok"
}

func main() {
	for _, c := range cases {
		fmt.Printf("%s default=%s strict=%s\n", c.name, decode(c.in, false), decode(c.in, true))
	}
}
