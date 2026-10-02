// Go reference for tests/v2/atlas.tin: prints the same lines for the same inputs, with Go's maps package.
package main

import (
	"fmt"
	"maps"
	"slices"
)

type pt struct{ x, y int64 }

func eqNumStr(a int64, b string) bool { return string(rune(a+48)) == b }
func bigOrZ(k string, v int64) bool   { return v > 50 || k == "z" }
func odd(k int64, v bool) bool        { return k%2 == 1 }

func main() {
	m := map[string]int64{"b": 2, "a": 1, "c": 3}
	keys := slices.Sorted(maps.Keys(m))
	vals := slices.Sorted(maps.Values(m))
	fmt.Println("keys", keys, vals, keys, len(m))

	c := maps.Clone(m)
	c["d"] = 4
	fmt.Println("clone", m, c, len(m), len(c))
	maps.Copy(c, map[string]int64{"a": 100, "z": 26})
	fmt.Println("copy", c)

	fmt.Println("equal", maps.Equal(m, maps.Clone(m)), maps.Equal(m, c), maps.Equal(map[string]int64{}, map[string]int64{}),
		maps.Equal(map[string]int64{"a": 0}, map[string]int64{"b": 0}), maps.Equal(map[string]int64{"a": 0}, map[string]int64{"a": 0}),
		maps.Equal(map[string]int64{"a": 1, "b": 2}, map[string]int64{"b": 2, "a": 1}))
	fmt.Println("equalfunc", maps.EqualFunc(m, map[string]string{"a": "1", "b": "2", "c": "3"}, eqNumStr),
		maps.EqualFunc(m, map[string]string{"a": "1", "b": "2", "c": "9"}, eqNumStr),
		maps.EqualFunc(m, map[string]string{"a": "1", "b": "2", "x": "3"}, eqNumStr))

	maps.DeleteFunc(c, bigOrZ)
	fmt.Println("deletefunc", c, len(c))
	maps.DeleteFunc(c, bigOrZ)
	fmt.Println("deletefunc again", c)

	flags := map[int64]bool{1: true, 2: false, 3: true, 4: true, 5: false}
	maps.DeleteFunc(flags, odd)
	fmt.Println("int keys", flags, slices.Sorted(maps.Keys(flags)))

	pts := map[pt]string{{1, 2}: "a", {3, 4}: "b"}
	cp := maps.Clone(pts)
	cp[pt{5, 6}] = "c"
	fmt.Println("struct keys", len(pts), len(cp), maps.Equal(pts, cp), maps.Equal(pts, maps.Clone(pts)))

	floats := map[float64]int64{2.5: 1, -1: 2, 0: 3}
	fmt.Println("float keys", slices.Sorted(maps.Keys(floats)), len(floats), floats[2.5], len(maps.Clone(floats)))
	empty := map[string]int64{}
	fmt.Println("empty", slices.Sorted(maps.Keys(empty)), slices.Sorted(maps.Values(empty)), slices.Sorted(maps.Keys(empty)), maps.Clone(empty), len(maps.Clone(empty)))
}
