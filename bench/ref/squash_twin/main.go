// Go side of tools/ci/squash_twin_check.py (#448): inflates Tin's raw DEFLATE of DIR/input.bin
// (DIR/tin1.deflate, tin6, tin9) with compress/flate, and writes Go's own (DIR/go1.deflate, go6,
// go9) for Tin to inflate. The input makes DEFLATE use every length and distance code, so a
// wrong entry in Tin's tables, which its encoder and decoder share, shows here.
package main

import (
	"bytes"
	"compress/flate"
	"fmt"
	"hash/crc32"
	"io"
	"os"
	"path/filepath"
)

func main() {
	dir := os.Args[1]
	in, err := os.ReadFile(filepath.Join(dir, "input.bin"))
	if err != nil {
		panic(err)
	}
	for _, lv := range []int{1, 6, 9} {
		z, err := os.ReadFile(filepath.Join(dir, fmt.Sprintf("tin%d.deflate", lv)))
		if err != nil {
			panic(err)
		}
		out, err := io.ReadAll(flate.NewReader(bytes.NewReader(z)))
		switch {
		case err != nil:
			fmt.Println("go inflates tin level", lv, "FAIL", err)
		case !bytes.Equal(out, in):
			fmt.Println("go inflates tin level", lv, "FAIL", len(out), crc32.ChecksumIEEE(out), "want", len(in), crc32.ChecksumIEEE(in))
		default:
			fmt.Println("go inflates tin level", lv, "ok", len(out), crc32.ChecksumIEEE(out))
		}
		var b bytes.Buffer
		w, _ := flate.NewWriter(&b, lv)
		w.Write(in)
		w.Close()
		if err := os.WriteFile(filepath.Join(dir, fmt.Sprintf("go%d.deflate", lv)), b.Bytes(), 0o644); err != nil {
			panic(err)
		}
	}
}
