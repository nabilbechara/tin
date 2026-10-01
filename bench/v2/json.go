package main

import (
	"encoding/json"
	"fmt"
)

type Item struct {
	ID   int64
	Name string
	Qty  uint32
	Tags []string
	OK   bool
	Note string
}

func main() {
	items := make([]Item, 0, 10)
	for i := int64(0); i < 10; i++ {
		items = append(items, Item{ID: i * 7919, Name: fmt.Sprintf("item-%d", i), Qty: uint32(i * 3), Tags: []string{"a", "bb", fmt.Sprintf("t%d", i)}, OK: i%2 == 0, Note: "quote \"here\" and\nnewline"})
	}
	var b []byte
	total := 0
	for i := 0; i < 1000000; i++ {
		var err error
		b, err = json.Marshal(items)
		if err != nil {
			panic(err)
		}
		total += len(b)
	}
	fmt.Println(total)
	fmt.Println(string(b))
}
