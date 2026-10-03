// Go reference twin for tests/v2/shapes_dispatch.tin
//
// The Tin test and this program are one description: the same Buf, the same Stack, the
// same generic functions over a Reader, a Writer, their composition, an ordered union
// and a Sized method set. Go reaches them through interfaces; Tin reaches them through
// structural shapes, monomorphized. The printed lines must be identical.
package main

import "fmt"

type Reader interface {
	Read(buf []uint8) (int64, error)
}

type Writer interface {
	Write(data []uint8) (int64, error)
}

type ReadWriter interface {
	Reader
	Writer
}

type Ordered interface {
	~int64 | ~float64 | ~string
}

type Sized interface {
	Len() int64
}

type Stack[T any] struct{ xs []T }

func (s *Stack[T]) Push(v T) {
	s.xs = append(s.xs, v)
}

func (s *Stack[T]) Len() int64 {
	return int64(len(s.xs))
}

type Buf struct{ data []uint8 }

func (b Buf) Read(buf []uint8) (int64, error) {
	n := len(b.data)
	i := 0
	for i < n && i < len(buf) {
		buf[i] = b.data[i]
		i++
	}
	return int64(i), nil
}

func (b Buf) Write(data []uint8) (int64, error) {
	return int64(len(data)), nil
}

func Drain[R Reader](r R) (int64, error) {
	buf := make([]uint8, 8)
	return r.Read(buf)
}

func Emit[W Writer](w W, s []uint8) (int64, error) {
	return w.Write(s)
}

func Both[RW ReadWriter](rw RW) (int64, error) {
	n, err := Drain(rw)
	if err != nil {
		return -1, err
	}
	m, err := Emit(rw, []uint8{1, 2})
	if err != nil {
		return -1, err
	}
	return n + m, nil
}

func Copy[R Reader, W Writer](dst W, src R) (int64, error) {
	buf := make([]uint8, 8)
	n, err := src.Read(buf)
	if err != nil {
		return -1, err
	}
	return dst.Write(buf[:n])
}

func Log(w Writer, msg []uint8) (int64, error) {
	return w.Write(msg)
}

func InOrder[T Ordered](a, b T) int64 {
	if a == b {
		return 0
	}
	if a < b {
		return -1
	}
	return 1
}

func Size[S Sized](s S) int64 {
	return s.Len()
}

func main() {
	b := Buf{data: []uint8{1, 2, 3}}
	n, _ := Drain(b)
	fmt.Println("read:", n)
	w, _ := Emit(b, []uint8{9, 9})
	fmt.Println("write:", w)
	both, _ := Both(b)
	fmt.Println("both:", both)
	copied, _ := Copy(b, b)
	fmt.Println("copy:", copied)
	logged, _ := Log(b, []uint8{4, 5, 6})
	fmt.Println("log:", logged)
	fmt.Println("i64:", InOrder[int64](1, 2))
	fmt.Println("str:", InOrder("b", "a"))
	fmt.Println("f64:", InOrder(2.5, 2.5))
	st := &Stack[int64]{}
	st.Push(7)
	st.Push(8)
	st.Push(9)
	fmt.Println("size:", Size(st))
	fmt.Println("len:", st.Len())
}
