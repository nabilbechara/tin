// The Go version of examples/demo.tin: the same five steps, same algorithms and sizes.
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"slices"
	"strings"
	"time"
)

type User struct {
	ID    int64    `json:"id"`
	Name  string   `json:"name"`
	Email string   `json:"email"`
	Score float64  `json:"score"`
	Tags  []string `json:"tags"`
}

func seconds(t0 time.Time) float64 {
	return time.Since(t0).Seconds()
}

// primes counts the primes below n with a sieve of Eratosthenes.
func primes(n int64) int64 {
	composite := make([]uint8, n)
	count := int64(0)
	for i := int64(2); i < n; i++ {
		if composite[i] == 0 {
			count++
			for j := i * i; j < n; j += i {
				composite[j] = 1
			}
		}
	}
	return count
}

func main() {
	total := time.Now()

	t := time.Now()
	p := primes(50000000)
	fmt.Printf("primes below 50M:     %d  (%.3f s)\n", p, seconds(t))

	t = time.Now()
	xs := make([]int64, 0, 5000000)
	x := uint64(88172645463325252)
	for i := 0; i < 5000000; i++ {
		x ^= x << 13
		x ^= x >> 7
		x ^= x << 17
		xs = append(xs, int64(x>>1))
	}
	slices.Sort(xs)
	fmt.Printf("sort 5M numbers:      sorted=%v  (%.3f s)\n", slices.IsSorted(xs), seconds(t))

	t = time.Now()
	block := []byte(strings.Repeat("0", 1048576))
	digest := ""
	for i := 0; i < 100; i++ {
		sum := sha256.Sum256(block)
		digest = hex.EncodeToString(sum[:])
	}
	fmt.Printf("sha256 of 100 MB:     %s...  (%.3f s)\n", digest[:16], seconds(t))

	t = time.Now()
	users := make([]User, 0, 200000)
	for i := 0; i < 200000; i++ {
		users = append(users, User{ID: int64(i), Name: fmt.Sprintf("user%d", i), Email: fmt.Sprintf("u%d@example.com", i), Score: float64(i) * 0.5, Tags: []string{"a", "b"}})
	}
	buf, _ := json.Marshal(users)
	back := []User{}
	err := json.Unmarshal(buf, &back)
	fmt.Printf("json 200k users:      %d MB, decoded %d, ok=%v  (%.3f s)\n", len(buf)>>20, len(back), err == nil, seconds(t))

	t = time.Now()
	m := make(map[int64]int64)
	for i := int64(0); i < 2000000; i++ {
		m[i*7] = i
	}
	hits := 0
	for i := int64(0); i < 4000000; i++ {
		if _, ok := m[i*7]; ok {
			hits++
		}
	}
	fmt.Printf("map 2M inserts, 4M lookups: hits=%d  (%.3f s)\n", hits, seconds(t))

	fmt.Printf("total:                %.3f s\n", seconds(total))
}
