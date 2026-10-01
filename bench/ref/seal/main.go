package main

import (
	"crypto/hmac"
	"crypto/sha1"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
)

func main() {
	ins := []string{"", "abc", "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq", fmt.Sprintf("%055d", 1), fmt.Sprintf("%056d", 1), fmt.Sprintf("%064d", 1), fmt.Sprintf("%1000d", 5)}
	for _, s := range ins {
		a := sha256.Sum256([]byte(s))
		b := sha1.Sum([]byte(s))
		fmt.Println(len(s), hex.EncodeToString(a[:]), hex.EncodeToString(b[:]))
	}
	m := hmac.New(sha256.New, []byte("Jefe"))
	m.Write([]byte("what do ya want for nothing?"))
	m2 := hmac.New(sha256.New, []byte(fmt.Sprintf("%0100d", 3)))
	m2.Write([]byte("msg"))
	fmt.Println("hmac", hex.EncodeToString(m.Sum(nil)), hex.EncodeToString(m2.Sum(nil)))
	for _, d := range []string{"", "f", "fo", "foo", "foob", "fooba", "foobar", "\xff\xfe\x00?>"} {
		b := []byte(d)
		std := base64.StdEncoding.EncodeToString(b)
		url := base64.RawURLEncoding.EncodeToString(b)
		back, e1 := base64.StdEncoding.DecodeString(std)
		back2, e2 := base64.RawURLEncoding.DecodeString(url)
		hx := hex.EncodeToString(b)
		back3, e3 := hex.DecodeString(hx)
		fmt.Println(fmt.Sprintf("%q", std), fmt.Sprintf("%q", url), hx, string(back) == d, e1 == nil, string(back2) == d, e2 == nil, string(back3) == d, e3 == nil)
	}
	for _, s := range []string{"Zg=", "Zm9v!", "Zh==", "====", "Zg==Zg=="} {
		_, err := base64.StdEncoding.Strict().DecodeString(s)
		fmt.Println("bad64", fmt.Sprintf("%q", s), err != nil)
	}
	_, eh := hex.DecodeString("abc")
	_, eh2 := hex.DecodeString("zz")
	fmt.Println("badhex", eh != nil, eh2 != nil)
	fmt.Println("cteq", hmac.Equal([]byte("abc"), []byte("abc")), hmac.Equal([]byte("abc"), []byte("abd")), hmac.Equal([]byte("a"), []byte("ab")))
	fmt.Println("random", 32, false)
}
