package main

import (
	"encoding/binary"
	"fmt"
	"hash/adler32"
	"hash/crc32"
	"hash/fnv"
	"math/bits"
)

const (
	p1 uint64 = 11400714785074694791
	p2 uint64 = 14029467366897019727
	p3 uint64 = 1609587929392839161
	p4 uint64 = 9650029242287828579
	p5 uint64 = 2870177450012600261
)

func round(acc, v uint64) uint64 { acc += v * p2; acc = bits.RotateLeft64(acc, 31); return acc * p1 }
func merge(acc, v uint64) uint64  { acc ^= round(0, v); return acc*p1 + p4 }

func xxh64(b []byte, seed uint64) uint64 {
	n := len(b)
	i := 0
	var h uint64
	if n >= 32 {
		v1, v2, v3, v4 := seed+p1+p2, seed+p2, seed, seed-p1
		for ; i+32 <= n; i += 32 {
			v1 = round(v1, binary.LittleEndian.Uint64(b[i:]))
			v2 = round(v2, binary.LittleEndian.Uint64(b[i+8:]))
			v3 = round(v3, binary.LittleEndian.Uint64(b[i+16:]))
			v4 = round(v4, binary.LittleEndian.Uint64(b[i+24:]))
		}
		h = bits.RotateLeft64(v1, 1) + bits.RotateLeft64(v2, 7) + bits.RotateLeft64(v3, 12) + bits.RotateLeft64(v4, 18)
		h = merge(h, v1)
		h = merge(h, v2)
		h = merge(h, v3)
		h = merge(h, v4)
	} else {
		h = seed + p5
	}
	h += uint64(n)
	for ; i+8 <= n; i += 8 {
		h ^= round(0, binary.LittleEndian.Uint64(b[i:]))
		h = bits.RotateLeft64(h, 27)*p1 + p4
	}
	if i+4 <= n {
		h ^= uint64(binary.LittleEndian.Uint32(b[i:])) * p1
		h = bits.RotateLeft64(h, 23)*p2 + p3
		i += 4
	}
	for ; i < n; i++ {
		h ^= uint64(b[i]) * p5
		h = bits.RotateLeft64(h, 11) * p1
	}
	h ^= h >> 33
	h *= p2
	h ^= h >> 29
	h *= p3
	h ^= h >> 32
	return h
}

func f32(s string) uint32 { h := fnv.New32a(); h.Write([]byte(s)); return h.Sum32() }
func f64(s string) uint64 { h := fnv.New64a(); h.Write([]byte(s)); return h.Sum64() }

func main() {
	cc := crc32.MakeTable(crc32.Castagnoli)
	ins := []string{"", "a", "abc", "123456789", "The quick brown fox jumps over the lazy dog", "0123456789abcdef0123456789abcdef0123456789", fmt.Sprintf("%0200d", 7)}
	for _, s := range ins {
		b := []byte(s)
		fmt.Printf("%d crc32=%08x crc32c=%08x fnv32a=%08x fnv64a=%016x adler=%08x xxh64=%016x xxh64s=%016x\n", len(s), crc32.ChecksumIEEE(b), crc32.Checksum(b, cc), f32(s), f64(s), adler32.Checksum(b), xxh64(b, 0), xxh64(b, 2654435761))
	}
	fmt.Printf("update %08x %08x\n", crc32.Update(crc32.ChecksumIEEE([]byte("hello ")), crc32.IEEETable, []byte("world")), crc32.ChecksumIEEE([]byte("hello world")))
	big := []byte{}
	for i := 0; i < 100000; i++ {
		big = append(big, byte(i*7))
	}
	fmt.Printf("big crc32=%08x crc32c=%08x adler=%08x xxh64=%016x\n", crc32.ChecksumIEEE(big), crc32.Checksum(big, cc), adler32.Checksum(big), xxh64(big, 0))
}
