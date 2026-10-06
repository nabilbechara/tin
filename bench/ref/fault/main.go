// Reference for toolchain/tests/v2/fault_chains.tin: Wrap, Is, Cause and Join through Go's errors
// package (Wrap is fmt.Errorf("%s: %w"), Cause is errors.Unwrap). Run with go run; the
// sorted output must equal toolchain/tests/v2/fault_chains.out.
package main

import (
	"errors"
	"fmt"
)

var ErrNotFound = errors.New("not found")
var ErrAlsoNotFound = errors.New("not found")
var ErrDenied = errors.New(fmt.Sprintf("denied %d", 1+1))

// The Tin runtime's sentinels, with Tin's messages.
var (
	Canceled         = errors.New("canceled")
	DeadlineExceeded = errors.New("deadline exceeded")
	LimitExceeded    = errors.New("limit exceeded")
	Overloaded       = errors.New("overloaded")
	Draining         = errors.New("draining")
	Panic            = errors.New("panic")
)

type Item struct{ Name string }

func Wrap(err error, msg string) error {
	if err == nil {
		return nil
	}
	return fmt.Errorf("%s: %w", msg, err)
}

func Message(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}

func find(key string) (Item, error) {
	switch key {
	case "missing":
		return Item{}, ErrNotFound
	case "secret":
		return Item{}, ErrDenied
	case "bad":
		return Item{}, errors.New("bad key " + key)
	}
	return Item{Name: key}, nil
}

func load(id int, key string) (Item, error) {
	it, err := find(key)
	if err != nil {
		return Item{}, Wrap(err, fmt.Sprintf("loading user %d", id))
	}
	return it, nil
}

func handle(key string) (string, error) {
	it, err := load(7, key)
	if err != nil {
		return "", Wrap(err, "handle")
	}
	return it.Name, nil
}

func classify(err error) string {
	switch {
	case err == nil:
		return "ok"
	case errors.Is(err, ErrNotFound):
		return "404"
	case errors.Is(err, DeadlineExceeded), errors.Is(err, Overloaded):
		return "503"
	case errors.Is(err, ErrDenied):
		return "403"
	}
	return "500"
}

func q(s string) string { return fmt.Sprintf("%q", s) }

func main() {
	_, err := handle("missing")
	fmt.Println("wrap message:", err)
	fmt.Println("wrap str:", err.Error())
	fmt.Println("wrap interp: " + err.Error())
	fmt.Println("wrap is ErrNotFound:", errors.Is(err, ErrNotFound))
	fmt.Println("wrap is ErrAlsoNotFound:", errors.Is(err, ErrAlsoNotFound))
	fmt.Println("wrap is ErrDenied:", errors.Is(err, ErrDenied))
	fmt.Println("wrap classify:", classify(err))
	c := errors.Unwrap(err)
	fmt.Println("cause 1:", c)
	c2 := errors.Unwrap(c)
	fmt.Println("cause 2:", c2, errors.Is(c2, ErrNotFound))
	c3 := errors.Unwrap(c2)
	fmt.Println("cause 3 nil:", c3 == nil)
	fmt.Println("message:", Message(err))

	_, err2 := handle("secret")
	fmt.Println("denied:", err2, classify(err2))
	_, err3 := handle("bad")
	fmt.Println("plain:", err3, classify(err3), errors.Is(err3, ErrNotFound))
	_, err4 := handle("ok")
	fmt.Println("success:", classify(err4), errors.Is(err4, nil), errors.Is(err4, ErrNotFound))

	a := errors.New("same text")
	b := errors.New("same text")
	fmt.Println("plain self:", errors.Is(a, a), "plain other:", errors.Is(a, b))
	wa := Wrap(a, "outer")
	fmt.Println("plain through wrap:", errors.Is(wa, a), errors.Is(wa, b))
	fmt.Println("nil target:", errors.Is(a, nil), "nil err:", errors.Is(nil, ErrNotFound))
	fmt.Println("sentinel self:", errors.Is(ErrNotFound, ErrNotFound), errors.Is(ErrNotFound, ErrAlsoNotFound))

	wn := Wrap(nil, "context")
	fmt.Println("wrap nil:", wn == nil, q(Message(nil)))
	ws := Wrap(ErrNotFound, "")
	fmt.Println("wrap empty msg:", q(Message(ws)), errors.Is(ws, ErrNotFound))

	d := Wrap(DeadlineExceeded, "dialing db")
	j := errors.Join(err, nil, d)
	fmt.Println("join message:", q(Message(j)))
	fmt.Println("join is:", errors.Is(j, ErrNotFound), errors.Is(j, DeadlineExceeded), errors.Is(j, ErrDenied), errors.Is(j, Canceled))
	fmt.Println("join cause nil:", errors.Unwrap(j) == nil)
	fmt.Println("join classify:", classify(j))
	jn := errors.Join(nil, nil)
	fmt.Println("join all nil:", jn == nil)
	je := errors.Join()
	fmt.Println("join empty:", je == nil)
	j1 := errors.Join(ErrDenied)
	fmt.Println("join one:", q(Message(j1)), errors.Is(j1, ErrDenied))
	wj := Wrap(j, "request")
	fmt.Println("wrapped join:", q(Message(wj)), errors.Is(wj, DeadlineExceeded), classify(wj))
	nested := errors.Join(errors.Join(a, ErrDenied), Overloaded)
	fmt.Println("nested join:", q(Message(nested)), errors.Is(nested, a), errors.Is(nested, ErrDenied), errors.Is(nested, Overloaded), errors.Is(nested, b))

	fmt.Println("sentinels:", Canceled, "|", DeadlineExceeded, "|", LimitExceeded, "|", Overloaded, "|", Draining, "|", Panic)
	fmt.Println("sentinels distinct:", errors.Is(Canceled, DeadlineExceeded), errors.Is(Draining, Canceled), errors.Is(LimitExceeded, LimitExceeded))
	fmt.Println("deadline text:", DeadlineExceeded.Error() == "deadline exceeded")
	fmt.Println("backtrace none:", q(""))

	// keep is a deep copy that keeps identities: in Go the value itself.
	k := wj
	fmt.Println("kept:", q(Message(k)), errors.Is(k, ErrNotFound), errors.Is(k, DeadlineExceeded), errors.Is(k, ErrDenied))

	f := fmt.Errorf("code %d", 42)
	fmt.Println("say.Fault:", f, errors.Is(Wrap(f, "x"), f))
	fmt.Println("error method:", err.Error())
}
