// Go reference for toolchain/tests/v2/squash.tin: prints the same lines for the same inputs, with Go's
// compress/flate, compress/gzip and compress/zlib.
package main

import (
	"bytes"
	"compress/flate"
	"compress/gzip"
	"compress/zlib"
	"encoding/hex"
	"fmt"
	"hash/crc32"
	"io"
)

func text(n int) []byte {
	var b []byte
	for i := 0; len(b) < n; i++ {
		b = append(b, []byte(fmt.Sprintf("record %d: the quick brown fox %d; ", i, i*7%13))...)
	}
	return b[:n]
}

func noise(n int) []byte {
	b := make([]byte, n)
	x := uint64(12345)
	for i := range b {
		x = x*6364136223846793005 + 1442695040888963407
		b[i] = byte(x >> 56)
	}
	return b
}

func hx(h string) []byte {
	b, _ := hex.DecodeString(h)
	return b
}

func inflate(kind string, data []byte) ([]byte, error) {
	var r io.Reader
	var err error
	switch kind {
	case "gzip":
		r, err = gzip.NewReader(bytes.NewReader(data))
	case "zlib":
		r, err = zlib.NewReader(bytes.NewReader(data))
	default:
		r = flate.NewReader(bytes.NewReader(data))
	}
	if err != nil {
		return nil, err
	}
	return io.ReadAll(r)
}

func decode(label, kind string, data []byte) {
	s, err := inflate(kind, data)
	if err != nil {
		fmt.Println(label, "error")
		return
	}
	fmt.Println(label, len(s), crc32.ChecksumIEEE(s))
}

func compress(kind string, s []byte, level int) []byte {
	var b bytes.Buffer
	var w io.WriteCloser
	switch kind {
	case "gzip":
		w, _ = gzip.NewWriterLevel(&b, level)
	case "zlib":
		w, _ = zlib.NewWriterLevel(&b, level)
	default:
		w, _ = flate.NewWriter(&b, level)
	}
	w.Write(s)
	w.Close()
	return b.Bytes()
}

// limited is what squash's max does: the decoder fails once the output would pass max.
func limited(kind string, data []byte, max int) bool {
	s, err := inflate(kind, data)
	return err == nil && len(s) > max
}

func main() {
	decode("go gzip two members", "gzip", hx("1f8b08000000000002ff84d15d0ac2400c04e0abe4089dee4f5bbd8d7545115c5c143dbe2f92bc4cc8fb47c8cc8cb6f77196e920af6b93e7fbb6dfe534fae72197fe95e9287f000e160533075090385815640e660585834d41e52029589c272de7ca4556b039272c289c328b09a74d5856387d561329dc2c47a3a144aba146b38196fa0b0000ffffdc529ee5580200001f8b08000000000004ff002c01d3fe1c43e2d5538fcb64d030fdfb29d37a55a95f615c0716388aa783da414b74f3080ce7c3487c362f11d74a2a0ecc52da0284baebc2378f59037b3553ce2820e9db8bb2829219b5f81fdc4966b1e6d19d2d46176c9aae1b83d6fab0f7f63be9d606b12ac9c39ebfb425c6af2cdff78607064eb3caa1873d55194f23db8c6074e924cec00b7ffdbe4e15897c8f9d97961d883f759b179cf3ac27b3337fb22ae15e88000b963ffabd51234cda8001a5abf651691ead5ef873151ad479a28924f01fcaa37173ff2d467468f9468d0020a81ce23cf9f493fdb81968cb812b0cc8efe9d0485fab715f7a756a282717964880c0c3f745341439e872ab31e01b954dfc391f8daaea459253c99e1b7db48cb153e5d889f3ece5a6328500c686f1e8c5304f7129766ca10845a927c4f0ece8010000ffff57bff1a02c010000"))
	decode("go gzip with name comment extra", "gzip", hx("1f8b081c0000000000ff020078796e6f7465732e747874006120636f6d6d656e74002a4a4dce2f4a5130b05228c94855282ccd4cce56482aca2fcf5348cbaf5030b056802a30c4aec01caec008bb02436b852240000000ffff0b36177c64000000"))
	decode("go zlib", "zlib", hx("789c74d14b0a02311084e1abf411a667262fbd8d31a2080683a2c77723dd5954ed3f42eaefd16a1f67590ef2ba3679be6ff52ea7d13f0fb9f4af2c47f903c52019583150031b06d9c08ec16a2060500c440c3603897cd277662c7603853ce14395c40c2e484df5ad4a7a461724e8743352d48fa624e9348634f5b3298cfa0b0000ffff7446c800"))
	decode("go deflate stored", "deflate", hx("002c01d3fe1c43e2d5538fcb64d030fdfb29d37a55a95f615c0716388aa783da414b74f3080ce7c3487c362f11d74a2a0ecc52da0284baebc2378f59037b3553ce2820e9db8bb2829219b5f81fdc4966b1e6d19d2d46176c9aae1b83d6fab0f7f63be9d606b12ac9c39ebfb425c6af2cdff78607064eb3caa1873d55194f23db8c6074e924cec00b7ffdbe4e15897c8f9d97961d883f759b179cf3ac27b3337fb22ae15e88000b963ffabd51234cda8001a5abf651691ead5ef873151ad479a28924f01fcaa37173ff2d467468f9468d0020a81ce23cf9f493fdb81968cb812b0cc8efe9d0485fab715f7a756a282717964880c0c3f745341439e872ab31e01b954dfc391f8daaea459253c99e1b7db48cb153e5d889f3ece5a6328500c686f1e8c5304f7129766ca10845a927c4f0ece8010000ffff"))
	decode("go deflate level 5", "deflate", hx("74d14b0a02311084e1abf411a667262fbd8d31a2080683a2c77723dd5954ed3f42eaefd16a1f67590ef2ba3679be6ff52ea7d13f0fb9f4af2c47f903c52019583150031b06d9c08ec16a2060500c440c3603897cd277662c7603853ce14395c40c2e484df5ad4a7a461724e8743352d48fa624e9348634f5b3298cfa0b0000ffff"))
	decode("tin gzip", "gzip", hx("1f8b08000000000000ff75d14b0a80300c45d1ad6409c67f7537d68a22582c8a2edf89241de4cd0fa5ef26051fd34cc540d71ae8bc37bfd394e273d0125f2a46fa01dba01350da80055436e805d4362805343670025a1b54023af049ddd9dba216e0c0133a9441cc4605a8c9ba9541cf5605089add0c14d5a331489a8d014df56c6c46fd00dc529ee558020000"))
	decode("tin zlib", "zlib", hx("78da012c01d3fe1c43e2d5538fcb64d030fdfb29d37a55a95f615c0716388aa783da414b74f3080ce7c3487c362f11d74a2a0ecc52da0284baebc2378f59037b3553ce2820e9db8bb2829219b5f81fdc4966b1e6d19d2d46176c9aae1b83d6fab0f7f63be9d606b12ac9c39ebfb425c6af2cdff78607064eb3caa1873d55194f23db8c6074e924cec00b7ffdbe4e15897c8f9d97961d883f759b179cf3ac27b3337fb22ae15e88000b963ffabd51234cda8001a5abf651691ead5ef873151ad479a28924f01fcaa37173ff2d467468f9468d0020a81ce23cf9f493fdb81968cb812b0cc8efe9d0485fab715f7a756a282717964880c0c3f745341439e872ab31e01b954dfc391f8daaea459253c99e1b7db48cb153e5d889f3ece5a6328500c686f1e8c5304f7129766ca10845a927c4f0ece85ebe970e"))
	decode("tin deflate", "deflate", hx("75d1b90d80400c44d1565c02c37d74c32510122b5620289f04d904e3fc25f3274e4388a324ad9ccb24c7b50e9bf431dcbbcce191a4930f80834a41ca0114641cd40a720e520505078d8292834c41c5016c67cd45aea0e10036144eccc2845313b6154ecfd28413d4b6c0296aa7c149fa1be334b5db40a3be"))
	decode("tin deflate stored", "deflate", hx("012c01d3fe1c43e2d5538fcb64d030fdfb29d37a55a95f615c0716388aa783da414b74f3080ce7c3487c362f11d74a2a0ecc52da0284baebc2378f59037b3553ce2820e9db8bb2829219b5f81fdc4966b1e6d19d2d46176c9aae1b83d6fab0f7f63be9d606b12ac9c39ebfb425c6af2cdff78607064eb3caa1873d55194f23db8c6074e924cec00b7ffdbe4e15897c8f9d97961d883f759b179cf3ac27b3337fb22ae15e88000b963ffabd51234cda8001a5abf651691ead5ef873151ad479a28924f01fcaa37173ff2d467468f9468d0020a81ce23cf9f493fdb81968cb812b0cc8efe9d0485fab715f7a756a282717964880c0c3f745341439e872ab31e01b954dfc391f8daaea459253c99e1b7db48cb153e5d889f3ece5a6328500c686f1e8c5304f7129766ca10845a927c4f0ece8"))

	names := []string{"text0", "text1", "text600", "text70000", "noise300", "noise70000", "zeros200000"}
	inputs := [][]byte{text(0), text(1), text(600), text(70000), noise(300), noise(70000), make([]byte, 200000)}
	for _, kind := range []string{"gzip", "zlib", "deflate"} {
		for i, s := range inputs {
			for _, lv := range []int{0, 1, 6, 9} {
				b, err := inflate(kind, compress(kind, s, lv))
				fmt.Println("roundtrip", kind, names[i], "level", lv, err == nil && bytes.Equal(b, s))
			}
		}
		big := text(70000)
		for _, lv := range []int{1, 6, 9} {
			fmt.Println("text70000 under a third", kind, "level", lv, len(compress(kind, big, lv)) < len(big)/3)
		}
		rnd := noise(70000)
		fmt.Println("noise70000 grows by at most 64 bytes", kind, len(compress(kind, rnd, 6)) <= len(rnd)+64)
		fmt.Println("limit", kind, limited(kind, compress(kind, big, 6), 1000))
		fmt.Println("no limit hit at the exact size", kind, !limited(kind, compress(kind, big, 6), 70000))
	}

	g := hx("1f8b08000000000000ff75d14b0a80300c45d1ad6409c67f7537d68a22582c8a2edf89241de4cd0fa5ef26051fd34cc540d71ae8bc37bfd394e273d0125f2a46fa01dba01350da80055436e805d4362805343670025a1b54023af049ddd9dba216e0c0133a9441cc4605a8c9ba9541cf5605089add0c14d5a331489a8d014df56c6c46fd00dc529ee558020000")
	bad := append([]byte{}, g...)
	bad[len(bad)/2] ^= 0x10
	decode("damaged gzip", "gzip", bad)
	z := hx("78da012c01d3fe1c43e2d5538fcb64d030fdfb29d37a55a95f615c0716388aa783da414b74f3080ce7c3487c362f11d74a2a0ecc52da0284baebc2378f59037b3553ce2820e9db8bb2829219b5f81fdc4966b1e6d19d2d46176c9aae1b83d6fab0f7f63be9d606b12ac9c39ebfb425c6af2cdff78607064eb3caa1873d55194f23db8c6074e924cec00b7ffdbe4e15897c8f9d97961d883f759b179cf3ac27b3337fb22ae15e88000b963ffabd51234cda8001a5abf651691ead5ef873151ad479a28924f01fcaa37173ff2d467468f9468d0020a81ce23cf9f493fdb81968cb812b0cc8efe9d0485fab715f7a756a282717964880c0c3f745341439e872ab31e01b954dfc391f8daaea459253c99e1b7db48cb153e5d889f3ece5a6328500c686f1e8c5304f7129766ca10845a927c4f0ece85ebe970e")
	decode("cut zlib", "zlib", z[:len(z)-5])
	decode("cut gzip", "gzip", g[:len(g)-3])
	decode("text is not gzip", "gzip", []byte("hello, world"))
	decode("empty is not gzip", "gzip", []byte{})
	decode("empty is not zlib", "zlib", []byte{})
}
