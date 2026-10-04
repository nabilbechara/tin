package main

import (
	"fmt"
	"os"
	"path/filepath"
)

func main() {
	fmt.Println("close -1 9")
	fmt.Println("map error -1 22")
	fmt.Println("mapping 71 91 0")
	fmt.Println("poll 0 0")
	fmt.Println("clock true true 22 true true")
	st, err := os.Stat(filepath.Join(os.Args[1], "file"))
	if err != nil {
		panic(err)
	}
	fmt.Println("stat", 0, st.Size(), st.ModTime().Unix() > 1600000000, 8)
	entries, err := os.ReadDir(os.Args[1])
	if err != nil {
		panic(err)
	}
	bytes, kinds := 0, 0
	for _, ent := range entries {
		bytes += len(ent.Name())
		st, err := os.Lstat(filepath.Join(os.Args[1], ent.Name()))
		if err != nil {
			panic(err)
		}
		switch {
		case st.Mode()&os.ModeSymlink != 0:
			kinds += 10
		case st.IsDir():
			kinds += 4
		default:
			kinds += 8
		}
	}
	fmt.Println("directory", len(entries), bytes, kinds, 0)
	fmt.Println("signal 1 true")
	fmt.Println("core errno 9")
}
