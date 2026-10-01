// Go reference for tests/v2/cairn.tin: prints the same lines for the same inputs.
package main

import (
	"container/heap"
	"container/list"
	"fmt"
	"math/bits"
	"slices"
)

func lcg(k int64) int64 {
	return k*6364136223846793005 + 1442695040888963407
}

type minHeap []int64

func (h minHeap) Len() int           { return len(h) }
func (h minHeap) Less(i, j int) bool { return h[i] < h[j] }
func (h minHeap) Swap(i, j int)      { h[i], h[j] = h[j], h[i] }
func (h *minHeap) Push(x any)        { *h = append(*h, x.(int64)) }
func (h *minHeap) Pop() any {
	old := *h
	n := len(old)
	x := old[n-1]
	*h = old[:n-1]
	return x
}

type maxHeap []int64

func (h maxHeap) Len() int           { return len(h) }
func (h maxHeap) Less(i, j int) bool { return h[i] > h[j] }
func (h maxHeap) Swap(i, j int)      { h[i], h[j] = h[j], h[i] }
func (h *maxHeap) Push(x any)        { *h = append(*h, x.(int64)) }
func (h *maxHeap) Pop() any {
	old := *h
	n := len(old)
	x := old[n-1]
	*h = old[:n-1]
	return x
}

func hpop(h *minHeap) (int64, bool) {
	if h.Len() == 0 {
		return 0, false
	}
	return heap.Pop(h).(int64), true
}

func hpeek(h *minHeap) (int64, bool) {
	if h.Len() == 0 {
		return 0, false
	}
	return (*h)[0], true
}

func mpop(h *maxHeap) (int64, bool) {
	if h.Len() == 0 {
		return 0, false
	}
	return heap.Pop(h).(int64), true
}

func mpeek(h *maxHeap) (int64, bool) {
	if h.Len() == 0 {
		return 0, false
	}
	return (*h)[0], true
}

// deque is a slice-backed double-ended queue with the same observable behaviour as cairn.IntDeque.
type deque struct{ xs []int64 }

func (d *deque) PushBack(v int64)  { d.xs = append(d.xs, v) }
func (d *deque) PushFront(v int64) { d.xs = append([]int64{v}, d.xs...) }
func (d *deque) PopFront() (int64, bool) {
	if len(d.xs) == 0 {
		return 0, false
	}
	v := d.xs[0]
	d.xs = d.xs[1:]
	return v, true
}
func (d *deque) PopBack() (int64, bool) {
	if len(d.xs) == 0 {
		return 0, false
	}
	v := d.xs[len(d.xs)-1]
	d.xs = d.xs[:len(d.xs)-1]
	return v, true
}
func (d *deque) Front() (int64, bool) {
	if len(d.xs) == 0 {
		return 0, false
	}
	return d.xs[0], true
}
func (d *deque) Back() (int64, bool) {
	if len(d.xs) == 0 {
		return 0, false
	}
	return d.xs[len(d.xs)-1], true
}
func (d *deque) At(i int) int64 { return d.xs[i] }
func (d *deque) Len() int       { return len(d.xs) }

type intSet struct{ m map[int64]bool }

func (s *intSet) Add(k int64) bool {
	if s.m == nil {
		s.m = map[int64]bool{}
	}
	if s.m[k] {
		return false
	}
	s.m[k] = true
	return true
}
func (s *intSet) Has(k int64) bool { return s.m[k] }
func (s *intSet) Del(k int64) bool {
	if !s.m[k] {
		return false
	}
	delete(s.m, k)
	return true
}
func (s *intSet) Len() int { return len(s.m) }
func (s *intSet) Keys() []int64 {
	out := make([]int64, 0, len(s.m))
	for k := range s.m {
		out = append(out, k)
	}
	return out
}

type strSet struct{ m map[string]bool }

func (s *strSet) Add(k string) bool {
	if s.m == nil {
		s.m = map[string]bool{}
	}
	if s.m[k] {
		return false
	}
	s.m[k] = true
	return true
}
func (s *strSet) Has(k string) bool { return s.m[k] }
func (s *strSet) Del(k string) bool {
	if !s.m[k] {
		return false
	}
	delete(s.m, k)
	return true
}
func (s *strSet) Len() int { return len(s.m) }
func (s *strSet) Keys() []string {
	out := make([]string, 0, len(s.m))
	for k := range s.m {
		out = append(out, k)
	}
	return out
}

type bitset struct{ words []uint64 }

func newBitset(n int) *bitset { return &bitset{words: make([]uint64, (n+63)/64)} }
func (b *bitset) Set(i int) {
	w := i >> 6
	for w >= len(b.words) {
		b.words = append(b.words, 0)
	}
	b.words[w] |= 1 << uint(i&63)
}
func (b *bitset) Clear(i int) {
	if i < 0 || i>>6 >= len(b.words) {
		return
	}
	b.words[i>>6] &^= 1 << uint(i&63)
}
func (b *bitset) Has(i int) bool {
	if i < 0 || i>>6 >= len(b.words) {
		return false
	}
	return b.words[i>>6]&(1<<uint(i&63)) != 0
}
func (b *bitset) Count() int {
	n := 0
	for _, w := range b.words {
		n += bits.OnesCount64(w)
	}
	return n
}
func (b *bitset) Next(i int) int {
	if i < 0 {
		i = 0
	}
	w := i >> 6
	if w >= len(b.words) {
		return -1
	}
	x := b.words[w] >> uint(i&63)
	if x != 0 {
		return i + bits.TrailingZeros64(x)
	}
	for w++; w < len(b.words); w++ {
		if b.words[w] != 0 {
			return w*64 + bits.TrailingZeros64(b.words[w])
		}
	}
	return -1
}
func (b *bitset) Len() int { return len(b.words) * 64 }

type entry struct{ k, v string }

type lru struct {
	cap int
	l   *list.List
	idx map[string]*list.Element
}

func newLRU(capacity int) *lru {
	if capacity < 1 {
		capacity = 1
	}
	return &lru{cap: capacity, l: list.New(), idx: map[string]*list.Element{}}
}
func (c *lru) Get(k string) (string, bool) {
	e, ok := c.idx[k]
	if !ok {
		return "", false
	}
	c.l.MoveToFront(e)
	return e.Value.(entry).v, true
}
func (c *lru) Peek(k string) (string, bool) {
	e, ok := c.idx[k]
	if !ok {
		return "", false
	}
	return e.Value.(entry).v, true
}
func (c *lru) Has(k string) bool { _, ok := c.idx[k]; return ok }
func (c *lru) Put(k, v string) {
	if e, ok := c.idx[k]; ok {
		e.Value = entry{k, v}
		c.l.MoveToFront(e)
		return
	}
	if c.l.Len() == c.cap {
		last := c.l.Back()
		delete(c.idx, last.Value.(entry).k)
		c.l.Remove(last)
	}
	c.idx[k] = c.l.PushFront(entry{k, v})
}
func (c *lru) Del(k string) bool {
	e, ok := c.idx[k]
	if !ok {
		return false
	}
	c.l.Remove(e)
	delete(c.idx, k)
	return true
}
func (c *lru) Len() int { return c.l.Len() }
func (c *lru) Cap() int { return c.cap }
func (c *lru) Keys() []string {
	out := make([]string, 0, c.l.Len())
	for e := c.l.Front(); e != nil; e = e.Next() {
		out = append(out, e.Value.(entry).k)
	}
	return out
}

func main() {
	h := &minHeap{}
	v, ok := hpop(h)
	fmt.Println("heap pop empty", v, ok, h.Len())
	v, ok = hpeek(h)
	fmt.Println("heap peek empty", v, ok)
	in := []int64{5, 3, 8, 1, 9, 2, 7, 3, -4, 9223372036854775807, -9223372036854775807 - 1, 0}
	for _, x := range in {
		heap.Push(h, x)
	}
	v, ok = hpeek(h)
	fmt.Println("heap peek", v, ok, h.Len())
	out := make([]int64, 0, 12)
	for h.Len() > 0 {
		v, ok = hpop(h)
		out = append(out, v)
	}
	fmt.Println("heap drain", out, slices.IsSorted(out), h.Len())
	heap.Push(h, int64(10))
	heap.Push(h, int64(4))
	v, ok = hpop(h)
	heap.Push(h, int64(1))
	v2, ok2 := hpop(h)
	v3, ok3 := hpop(h)
	v4, ok4 := hpop(h)
	fmt.Println("heap interleave", v, ok, v2, ok2, v3, ok3, v4, ok4, h.Len())
	hz := &minHeap{}
	k := int64(1)
	for i := 0; i < 1000; i++ {
		k = lcg(k)
		heap.Push(hz, (k>>30)%1000)
	}
	prev := int64(-9223372036854775807 - 1)
	okAll := true
	var cs int64
	for hz.Len() > 0 {
		v, ok = hpop(hz)
		if v < prev {
			okAll = false
		}
		prev = v
		cs = cs*31 + v
	}
	fmt.Println("heap stress", okAll, cs, hz.Len())

	m := &maxHeap{}
	v, ok = mpop(m)
	fmt.Println("maxheap pop empty", v, ok, m.Len())
	for _, x := range in {
		heap.Push(m, x)
	}
	v, ok = mpeek(m)
	fmt.Println("maxheap peek", v, ok, m.Len())
	out = out[:0]
	for m.Len() > 0 {
		v, ok = mpop(m)
		out = append(out, v)
	}
	fmt.Println("maxheap drain", out, m.Len())
	mz := &maxHeap{}
	k = 2
	for i := 0; i < 1000; i++ {
		k = lcg(k)
		heap.Push(mz, (k>>30)%1000)
	}
	prev = 9223372036854775807
	okAll = true
	cs = 0
	for mz.Len() > 0 {
		v, ok = mpop(mz)
		if v > prev {
			okAll = false
		}
		prev = v
		cs = cs*31 + v
	}
	fmt.Println("maxheap stress", okAll, cs)

	d := &deque{}
	v, ok = d.PopFront()
	v2, ok2 = d.PopBack()
	v3, ok3 = d.Front()
	v4, ok4 = d.Back()
	fmt.Println("deque empty", v, ok, v2, ok2, v3, ok3, v4, ok4, d.Len())
	d.PushBack(1)
	d.PushBack(2)
	d.PushFront(0)
	d.PushFront(-1)
	d.PushBack(3)
	fmt.Println("deque at", d.Len(), d.At(0), d.At(1), d.At(2), d.At(3), d.At(4))
	v, ok = d.Front()
	v2, ok2 = d.Back()
	fmt.Println("deque ends", v, ok, v2, ok2)
	v, ok = d.PopFront()
	v2, ok2 = d.PopBack()
	fmt.Println("deque pops", v, ok, v2, ok2, d.Len(), d.At(0), d.At(2))
	dz := &deque{}
	for i := 0; i < 100; i++ {
		dz.PushBack(int64(i))
	}
	for i := 0; i < 1000; i++ {
		x, xok := dz.PopFront()
		if xok {
			dz.PushBack(x)
		}
	}
	fmt.Println("deque rotate", dz.Len(), dz.At(0), dz.At(50), dz.At(99))
	for i := 0; i < 100; i++ {
		dz.PushFront(int64(-i))
	}
	fmt.Println("deque front", dz.Len(), dz.At(0), dz.At(99), dz.At(100), dz.At(199))
	var sum int64
	var cnt int64
	for dz.Len() > 0 {
		x, xok := dz.PopBack()
		if xok {
			sum += x
			cnt++
		}
	}
	fmt.Println("deque drain", cnt, sum, dz.Len())
	dz.PushFront(7)
	fmt.Println("deque reuse", dz.Len(), dz.At(0))

	q := &deque{}
	v, ok = q.PopFront()
	v2, ok2 = q.Front()
	fmt.Println("queue empty", v, ok, v2, ok2, q.Len())
	for i := 0; i < 10; i++ {
		q.PushBack(int64(i * i))
	}
	v, ok = q.Front()
	fmt.Println("queue peek", v, ok, q.Len())
	v, ok = q.PopFront()
	v2, ok2 = q.PopFront()
	q.PushBack(100)
	fmt.Println("queue pops", v, ok, v2, ok2, q.Len())
	outq := make([]int64, 0)
	for q.Len() > 0 {
		x, xok := q.PopFront()
		if xok {
			outq = append(outq, x)
		}
	}
	fmt.Println("queue drain", outq)
	qz := &deque{}
	sum = 0
	for i := 0; i < 1000; i++ {
		qz.PushBack(int64(i))
		if i%3 == 0 {
			x, xok := qz.PopFront()
			if xok {
				sum += x
			}
		}
	}
	v, ok = qz.Front()
	fmt.Println("queue stress", qz.Len(), sum, v, ok)

	s := &intSet{}
	fmt.Println("set add", s.Add(5), s.Add(5), s.Add(-7), s.Add(0), s.Add(9223372036854775807), s.Len())
	fmt.Println("set has", s.Has(5), s.Has(6), s.Has(-7), s.Has(0), s.Has(9223372036854775807), s.Has(-9223372036854775807-1))
	fmt.Println("set del", s.Del(5), s.Del(5), s.Has(5), s.Len())
	fmt.Println("set readd", s.Add(5), s.Len())
	keys := s.Keys()
	slices.Sort(keys)
	fmt.Println("set keys", keys)
	sz := &intSet{}
	ref := make([]int64, 0)
	k = 3
	for i := 0; i < 2000; i++ {
		k = lcg(k)
		x := (k >> 30) % 1500
		sz.Add(x)
		ref = append(ref, x)
	}
	slices.Sort(ref)
	ref = slices.Compact(ref)
	nref := len(ref)
	fmt.Println("set stress len", sz.Len(), nref)
	del := 0
	exp := make([]int64, 0)
	for _, x := range ref {
		if x%3 == 0 {
			if sz.Del(x) {
				del++
			}
		} else {
			exp = append(exp, x)
		}
	}
	keys2 := sz.Keys()
	slices.Sort(keys2)
	fmt.Println("set stress del", del, sz.Len(), slices.Equal(keys2, exp))
	hit := 0
	for x := int64(-1500); x <= 1500; x++ {
		if sz.Has(x) {
			hit++
		}
	}
	fmt.Println("set stress has", hit)
	for i := 0; i < 3000; i++ {
		sz.Add(int64(i + 10000))
	}
	fmt.Println("set stress grow", sz.Len(), sz.Has(10000), sz.Has(12999), sz.Has(13000), sz.Has(exp[0]))
	z := &intSet{}
	fmt.Println("set zero", z.Has(1), z.Del(1), z.Len(), len(z.Keys()), z.Add(1), z.Has(1), z.Len())

	ss := &strSet{}
	fmt.Println("strset add", ss.Add("a"), ss.Add("b"), ss.Add("a"), ss.Add(""), ss.Len())
	fmt.Println("strset has", ss.Has("a"), ss.Has("c"), ss.Has(""), ss.Del("a"), ss.Del("a"), ss.Has("a"), ss.Len())
	sk := ss.Keys()
	slices.Sort(sk)
	fmt.Println("strset keys", sk)
	zs := &strSet{}
	fmt.Println("strset zero", zs.Has("x"), zs.Len(), zs.Del("x"), len(zs.Keys()), zs.Add("x"), zs.Has("x"), zs.Len())
	k = 5
	for i := 0; i < 500; i++ {
		k = lcg(k)
		zs.Add(fmt.Sprintf("k%d", (k>>35)%300))
	}
	sk = zs.Keys()
	slices.Sort(sk)
	fmt.Println("strset stress", zs.Len(), sk[0], sk[len(sk)-1], zs.Has("x"))

	bs := newBitset(10)
	fmt.Println("bitset init", bs.Len(), bs.Count(), bs.Has(0), bs.Has(9), bs.Has(64), bs.Has(-1), bs.Next(0))
	bs.Set(0)
	bs.Set(9)
	bs.Set(63)
	bs.Set(64)
	bs.Set(200)
	fmt.Println("bitset set", bs.Len(), bs.Count(), bs.Has(0), bs.Has(9), bs.Has(63), bs.Has(64), bs.Has(65), bs.Has(200), bs.Has(201))
	fmt.Println("bitset next", bs.Next(0), bs.Next(1), bs.Next(9), bs.Next(10), bs.Next(63), bs.Next(64), bs.Next(65), bs.Next(200), bs.Next(201), bs.Next(-5), bs.Next(1000))
	bs.Clear(9)
	bs.Clear(64)
	bs.Clear(5000)
	bs.Clear(-1)
	fmt.Println("bitset clear", bs.Count(), bs.Has(9), bs.Has(64), bs.Next(1), bs.Next(64), bs.Len())
	all := make([]int64, 0)
	for i := bs.Next(0); i >= 0; i = bs.Next(i + 1) {
		all = append(all, int64(i))
	}
	fmt.Println("bitset iter", all)
	bz := &bitset{}
	for i := 0; i < 1000; i += 7 {
		bz.Set(i)
	}
	cnt = 0
	for i := bz.Next(0); i >= 0; i = bz.Next(i + 1) {
		cnt++
	}
	w := bz.words
	fmt.Println("bitset dense", bz.Count(), cnt, bz.Len(), bz.Next(995), bz.Next(1000), len(w), w[0])

	c := newLRU(2)
	gv, gok := c.Get("a")
	fmt.Println("lru empty", fmt.Sprintf("%q", gv), gok, c.Len(), c.Cap(), len(c.Keys()))
	c.Put("a", "1")
	c.Put("b", "2")
	gv, gok = c.Get("a")
	c.Put("c", "3")
	gv2, gok2 := c.Get("b")
	fmt.Println("lru evict", gv, gok, fmt.Sprintf("%q", gv2), gok2, c.Len(), c.Keys())
	c.Put("a", "11")
	gv, gok = c.Peek("c")
	gv2, gok2 = c.Peek("a")
	fmt.Println("lru update", c.Keys(), gv, gok, gv2, gok2, c.Has("a"), c.Has("b"))
	fmt.Println("lru del", c.Del("c"), c.Del("c"), c.Len(), c.Keys())
	c.Put("d", "4")
	c.Put("e", "5")
	fmt.Println("lru refill", c.Keys(), c.Has("a"), c.Len())
	gv, gok = c.Get("d")
	fmt.Println("lru get", gv, gok, c.Keys())
	c1 := newLRU(1)
	c1.Put("x", "1")
	c1.Put("y", "2")
	gv, gok = c1.Get("y")
	fmt.Println("lru one", c1.Keys(), c1.Has("x"), c1.Len(), gv, gok)
	c0 := newLRU(0)
	c0.Put("only", "v")
	c0.Put("only", "w")
	gv, gok = c0.Get("only")
	fmt.Println("lru zero cap", c0.Cap(), c0.Len(), gv, gok)
	cl := newLRU(100)
	k = 17
	hits := 0
	for i := 0; i < 1000; i++ {
		k = lcg(k)
		key := fmt.Sprintf("k%d", (k>>33)%150)
		if i%3 == 0 {
			_, hok := cl.Get(key)
			if hok {
				hits++
			}
		} else if i%7 == 0 {
			cl.Del(key)
		} else {
			cl.Put(key, fmt.Sprintf("v%d", i))
		}
	}
	fmt.Println("lru stress", cl.Len(), hits, cl.Keys())
	lk := cl.Keys()
	gv, gok = cl.Peek(lk[0])
	gv2, gok2 = cl.Peek(lk[len(lk)-1])
	fmt.Println("lru stress peek", gv, gok, gv2, gok2)
}
