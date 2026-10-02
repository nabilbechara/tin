package main

import (
	"fmt"
	"net/url"
)

func q(s string) string { return fmt.Sprintf("%q", s) }

func b(v bool) string { return fmt.Sprint(v) }

func show(label string, raw string, req bool) {
	var u *url.URL
	var err error
	if req {
		u, err = url.ParseRequestURI(raw)
	} else {
		u, err = url.Parse(raw)
	}
	if err != nil {
		fmt.Println(label, q(raw), "ERR", err.Error())
		return
	}
	pw, has := u.User.Password()
	fmt.Println(label, q(raw), q(u.String()), q(u.Scheme), q(u.Opaque), q(u.User.Username()), q(pw), b(has), q(u.Host), q(u.Hostname()), q(u.Port()),
		q(u.Path), q(u.RawPath), q(u.EscapedPath()), q(u.RawQuery), b(u.ForceQuery), q(u.Fragment), q(u.RawFragment), q(u.EscapedFragment()),
		b(u.OmitHost), q(u.RequestURI()), b(u.IsAbs()), q(u.Redacted()), q(u.Query().Encode()))
}

func resolve(base string, ref string) {
	bu, err := url.Parse(base)
	if err != nil {
		fmt.Println("resolve", q(base), q(ref), "BASEERR", err.Error())
		return
	}
	ru, err := url.Parse(ref)
	if err != nil {
		fmt.Println("resolve", q(base), q(ref), "REFERR", err.Error())
		return
	}
	r := bu.ResolveReference(ru)
	fmt.Println("resolve", q(base), q(ref), q(r.String()))
	p, err := bu.Parse(ref)
	if err != nil {
		fmt.Println("resolve-parse", q(base), q(ref), "ERR", err.Error())
		return
	}
	fmt.Println("resolve-parse", q(base), q(ref), q(p.String()))
}

func lenient(raw string) string {
	u, err := url.Parse("?" + raw)
	if err != nil {
		return "?"
	}
	return u.Query().Encode()
}

func query(raw string) {
	v, err := url.ParseQuery(raw)
	if err != nil {
		fmt.Println("query", q(raw), "ERR", err.Error(), q(lenient(raw)))
		return
	}
	fmt.Println("query", q(raw), q(v.Encode()), len(v), q(v.Get("a")), b(v.Has("a")), len(v["a"]))
}

func main() {
	for _, s := range []string{"http://www.google.com", "http://www.google.com/", "http://www.google.com/file%20one%26two", "ftp://webmaster@www.google.com/", "ftp://john%20doe@www.google.com/", "http://www.google.com/?q=go+language", "http://www.google.com/?q=go%20language", "http://www.google.com/a%20b?q=c+d", "http:www.google.com/?q=go+language", "http:%2f%2fwww.google.com/?q=go+language", "mailto:/webmaster@golang.org", "mailto:webmaster@golang.org", "/foo?query=http://bad", "//foo", "//user@foo/path?a=b", "///threeslashes", "http:///threeslashes", "file:///home/adg/rabbits", "file:///C:/FooBar/Baz.txt", "file:///", "file:/x", "x:", "x:/", "http://www.google.com/#frag", "http://www.google.com/#frag%20ment", "http://www.google.com/#a b", "http://www.google.com/#%zz", "http://www.google.com/?", "http://www.google.com?", "http://www.google.com/?#", "http://www.google.com/a?b?c", "http://[fe80::1]/", "http://[fe80::1]:8080/", "http://[fe80::1%25en0]/", "http://[fe80::1%25en0]:8080/", "http://[fe80::1%en0]/", "http://[::1", "http://[::1]x/", "http://[::1]:x/", "http://[1.2.3.4]/", "http://[::ffff:1.2.3.4]/", "http://[::ffff:1.2.3.4%25z]/", "http://[::1]:80:90/", "http://[:::1]/", "http://[1::2::3]/", "http://[12345::1]/", "http://[g::1]/", "http://[1:2:3:4:5:6:7:8:9]/", "http://[1:2:3:4:5:6:7]/", "http://[::1%25]/", "http://[1.2.3.4.5]/", "http://[1.02.3.4]/", "http://[::1.2.3]/", "http://[::256.1.1.1]/", "http://[fe80::1%25a%00]/", "http://[]/", "http://[%25]/", "http://a[b]c/", "http://host:80", "http://host:", "http://host:port/", "http://host:80:80/", "http://:80/", "postgres://user:pw@host1:5432,host2:5433/db", "postgresql://a,b/db", "http://user@host@evil/", "http://a@b@c/", "http://us%zzer@host/", "http://user:pass:word@host/", "http://user:@host/", "http://:pw@host/", "http://@host/", "http://us er@host/", "http://user%20name:p%3Aw@host/path", "http://host/%zz", "http://host/%", "http://host/%4", "http://ho%41st/", "http://ho%20st/", "http://ho st/", "http://host%25/", "http://héllo.com/", "http://host/päth", "http://host/a%2Fb", "http://host/a%2fb/c", "http://host/a/b%2", "http://host/a%3Ab", "http://host/a;b,c", "http://host/a$b&c", "http://host/a b", "http://host/a+b", "http://host/a%2bb", "http://host/*", "*", "", " ", "%", "a", "a/b", "a:b", "a:b/c", "1:b", "+a:b", "a+b.c-d:e", "./a:b", "a/b:c", "/a:b", "http://host/a?x=%zz", "http://host/a?x=1;y=2", "http://host/\x01", "http://host/", "http://host\n/", "http:", "http://", "http:///", "http://?q", "http://#f", "HTTP://HOST/PATH", "HtTp://Example.COM/A", ":foo", "://foo", "foo://", "//", "///", "////", "/..", "/a/../b", "../a", "?q=1", "#f", "?", "#", "a?b#c", "//host/path?query#frag", "//host:80", "x://[::1]", "sc:opaque?q#f", "sc://h/p?q#f", "sc:/p", "sc:///p", "sc://", "sc:?q", "sc:#f", "tel:+1-555-0100", "urn:isbn:0451450523", "http://host/%e4%b8%96%e7%95%8c", "http://host/世界", "http://host/?q=世界", "http://世界.com/", "http://host/a%20b%2Fc", "http://host/%7Euser", "http://host/~user", "http://host/a%21b", "http://host/a!b'c(d)e*f", "http://host/#a!b'c(d)e*f", "http://host/#a%21b", "http://host/#a/b?c", "http://host/#%e4%b8", "http://host/%41"} {
		show("parse", s, false)
	}
	for _, s := range []string{"/", "/a/b?c=d", "*", "", "http://h/p?q", "a/b", "//h/p", "/a#b", "/a b", "/a%zz", "///x", "http:", "x:y", "/\x01"} {
		show("request", s, true)
	}
	for _, s := range []string{"", "abc", "a b", "a+b", "a%b", "a/b", "a?b", "a&b=c", "a;b", "a,b", "a:b@c", "a~b_c-d.e", "a!b'c(d)e*f", "aéb", "世界", "a\x00b", "%41", "%zz", "%4", "%", "a%2", "%2g", "a+b%20c", "a%2Bb", "%e4%b8%96", "100%", "~", "$&+,/:;=?@", "[]<>\"{}|\\^`", "\t\n"} {
		fmt.Println("escape", q(s), q(url.QueryEscape(s)), q(url.PathEscape(s)))
		qu, err := url.QueryUnescape(s)
		if err != nil {
			fmt.Println("queryunescape", q(s), "ERR", err.Error())
			continue
		}
		fmt.Println("queryunescape", q(s), q(qu))
	}
	for _, s := range []string{"", "abc", "a b", "a+b", "a%b", "a/b", "a?b", "a&b=c", "a;b", "a,b", "a:b@c", "a~b_c-d.e", "a!b'c(d)e*f", "aéb", "世界", "a\x00b", "%41", "%zz", "%4", "%", "a%2", "%2g", "a+b%20c", "a%2Bb", "%e4%b8%96", "100%", "~", "$&+,/:;=?@", "[]<>\"{}|\\^`", "\t\n"} {
		pu, err := url.PathUnescape(s)
		if err != nil {
			fmt.Println("pathunescape", q(s), "ERR", err.Error())
			continue
		}
		fmt.Println("pathunescape", q(s), q(pu))
	}
	for _, ref := range []string{"g:h", "?", "?#s", "g", "./g", "g/", "/g", "//g", "?y", "g?y", "#s", "g#s", "g?y#s", ";x", "g;x", "g;x?y#s", "", ".", "./", "..", "../", "../g", "../..", "../../", "../../g", "../../../g", "../../../../g", "/./g", "/../g", "g.", ".g", "g..", "..g", "./../g", "./g/.", "g/./h", "g/../h", "g;x=1/./y", "g;x=1/../y", "g?y/./x", "g?y/../x", "g#s/./x", "g#s/../x", "http:g", "http://x/y", "//x", "/a%2fb", "a%2fb/../c", "g h", "%zz"} {
		resolve("http://a/b/c/d;p?q", ref)
	}
	for _, base := range []string{"http://a/b/c/", "http://a", "http://a/", "http://a/b", "/a/b", "a/b", "", "http://u:p@h:1/x?y#z", "mailto:a@b", "mailto:a@b?s=1", "http://a/b%2fc/d", "file:///a/b", "sc:opaque", "http://a/b/c/d?q#f"} {
		for _, ref := range []string{"x", "/x", "../x", "?z", "#z", "", "//h2/x", "mailto:c@d", "sc:other", "./", "..", "../..", "../../..", "u://h"} {
			resolve(base, ref)
		}
	}
	{
		r, err := url.JoinPath("http://h/a/b", []string{}...)
		if err != nil {
			fmt.Println("join", "http://h/a/b", "[]", "ERR", err.Error())
		} else {
			fmt.Println("join", "http://h/a/b", "[]", q(r))
		}
	}
	{
		r, err := url.JoinPath("http://h/a/b", []string{"c"}...)
		if err != nil {
			fmt.Println("join", "http://h/a/b", "[c]", "ERR", err.Error())
		} else {
			fmt.Println("join", "http://h/a/b", "[c]", q(r))
		}
	}
	{
		r, err := url.JoinPath("http://h/a/b/", []string{"c"}...)
		if err != nil {
			fmt.Println("join", "http://h/a/b/", "[c]", "ERR", err.Error())
		} else {
			fmt.Println("join", "http://h/a/b/", "[c]", q(r))
		}
	}
	{
		r, err := url.JoinPath("http://h/a/b", []string{"../c"}...)
		if err != nil {
			fmt.Println("join", "http://h/a/b", "[../c]", "ERR", err.Error())
		} else {
			fmt.Println("join", "http://h/a/b", "[../c]", q(r))
		}
	}
	{
		r, err := url.JoinPath("http://h/a/b", []string{"..", ".."}...)
		if err != nil {
			fmt.Println("join", "http://h/a/b", "[.. ..]", "ERR", err.Error())
		} else {
			fmt.Println("join", "http://h/a/b", "[.. ..]", q(r))
		}
	}
	{
		r, err := url.JoinPath("http://h/a/b", []string{"../../../.."}...)
		if err != nil {
			fmt.Println("join", "http://h/a/b", "[../../../..]", "ERR", err.Error())
		} else {
			fmt.Println("join", "http://h/a/b", "[../../../..]", q(r))
		}
	}
	{
		r, err := url.JoinPath("http://h", []string{"x"}...)
		if err != nil {
			fmt.Println("join", "http://h", "[x]", "ERR", err.Error())
		} else {
			fmt.Println("join", "http://h", "[x]", q(r))
		}
	}
	{
		r, err := url.JoinPath("http://h", []string{"", "x"}...)
		if err != nil {
			fmt.Println("join", "http://h", "[ x]", "ERR", err.Error())
		} else {
			fmt.Println("join", "http://h", "[ x]", q(r))
		}
	}
	{
		r, err := url.JoinPath("http://h/", []string{"x/"}...)
		if err != nil {
			fmt.Println("join", "http://h/", "[x/]", "ERR", err.Error())
		} else {
			fmt.Println("join", "http://h/", "[x/]", q(r))
		}
	}
	{
		r, err := url.JoinPath("http://h/a", []string{"b/", "c/"}...)
		if err != nil {
			fmt.Println("join", "http://h/a", "[b/ c/]", "ERR", err.Error())
		} else {
			fmt.Println("join", "http://h/a", "[b/ c/]", q(r))
		}
	}
	{
		r, err := url.JoinPath("http://h/a%2fb", []string{"c"}...)
		if err != nil {
			fmt.Println("join", "http://h/a%2fb", "[c]", "ERR", err.Error())
		} else {
			fmt.Println("join", "http://h/a%2fb", "[c]", q(r))
		}
	}
	{
		r, err := url.JoinPath("http://h/a", []string{"b c"}...)
		if err != nil {
			fmt.Println("join", "http://h/a", "[b c]", "ERR", err.Error())
		} else {
			fmt.Println("join", "http://h/a", "[b c]", q(r))
		}
	}
	{
		r, err := url.JoinPath("http://h/a", []string{"%zz"}...)
		if err != nil {
			fmt.Println("join", "http://h/a", "[%zz]", "ERR", err.Error())
		} else {
			fmt.Println("join", "http://h/a", "[%zz]", q(r))
		}
	}
	{
		r, err := url.JoinPath("a/b", []string{"c"}...)
		if err != nil {
			fmt.Println("join", "a/b", "[c]", "ERR", err.Error())
		} else {
			fmt.Println("join", "a/b", "[c]", q(r))
		}
	}
	{
		r, err := url.JoinPath("", []string{"c"}...)
		if err != nil {
			fmt.Println("join", "", "[c]", "ERR", err.Error())
		} else {
			fmt.Println("join", "", "[c]", q(r))
		}
	}
	{
		r, err := url.JoinPath("%zz", []string{"c"}...)
		if err != nil {
			fmt.Println("join", "%zz", "[c]", "ERR", err.Error())
		} else {
			fmt.Println("join", "%zz", "[c]", q(r))
		}
	}
	{
		r, err := url.JoinPath("http://h/a?q#f", []string{"b"}...)
		if err != nil {
			fmt.Println("join", "http://h/a?q#f", "[b]", "ERR", err.Error())
		} else {
			fmt.Println("join", "http://h/a?q#f", "[b]", q(r))
		}
	}
	{
		r, err := url.JoinPath("http://h/a", []string{"b?c"}...)
		if err != nil {
			fmt.Println("join", "http://h/a", "[b?c]", "ERR", err.Error())
		} else {
			fmt.Println("join", "http://h/a", "[b?c]", q(r))
		}
	}
	{
		r, err := url.JoinPath("mailto:a@b", []string{"c"}...)
		if err != nil {
			fmt.Println("join", "mailto:a@b", "[c]", "ERR", err.Error())
		} else {
			fmt.Println("join", "mailto:a@b", "[c]", q(r))
		}
	}
	{
		r, err := url.JoinPath("http://h/a", []string{"//b"}...)
		if err != nil {
			fmt.Println("join", "http://h/a", "[//b]", "ERR", err.Error())
		} else {
			fmt.Println("join", "http://h/a", "[//b]", q(r))
		}
	}
	{
		r, err := url.JoinPath("http://h/a", []string{"."}...)
		if err != nil {
			fmt.Println("join", "http://h/a", "[.]", "ERR", err.Error())
		} else {
			fmt.Println("join", "http://h/a", "[.]", q(r))
		}
	}
	{
		r, err := url.JoinPath("http://h/a/", []string{".."}...)
		if err != nil {
			fmt.Println("join", "http://h/a/", "[..]", "ERR", err.Error())
		} else {
			fmt.Println("join", "http://h/a/", "[..]", q(r))
		}
	}
	{
		r, err := url.JoinPath("http://h/", []string{".."}...)
		if err != nil {
			fmt.Println("join", "http://h/", "[..]", "ERR", err.Error())
		} else {
			fmt.Println("join", "http://h/", "[..]", q(r))
		}
	}
	query("")
	query("a=1")
	query("a=1&b=2")
	query("b=2&a=1&a=3")
	query("a")
	query("a=")
	query("=1")
	query("&&a=1&&")
	query("a=1;b=2")
	query("a=%zz")
	query("%zz=1")
	query("a=1&b=%zz&c=3")
	query("a+b=c+d")
	query("a%20b=c%2Bd")
	query("a=b=c")
	query("x=%e4%b8%96")
	query("k=v&k=v&k=w")
	query("é=ü")
	query("a=1&a=2&a=3&b=&c")
	query("a=%")
	query("a=%4")
	query("%=1")
	query("a=1;")
	query(";")
	query("a=1&;&b=2")
	query("a b=c d")
	query("?a=1")
	v := url.Values{}
	v.Set("a", "1")
	fmt.Println("values", q(v.Encode()), len(v), q(v.Get("a")), b(v.Has("b")), len(v["a"]), len(v["zz"]))
	v.Add("a", "2")
	fmt.Println("values", q(v.Encode()), len(v), q(v.Get("a")), b(v.Has("b")), len(v["a"]), len(v["zz"]))
	v.Add("b", "x y")
	fmt.Println("values", q(v.Encode()), len(v), q(v.Get("a")), b(v.Has("b")), len(v["a"]), len(v["zz"]))
	v.Set("c", "é&=+")
	fmt.Println("values", q(v.Encode()), len(v), q(v.Get("a")), b(v.Has("b")), len(v["a"]), len(v["zz"]))
	v.Add("a", "3")
	fmt.Println("values", q(v.Encode()), len(v), q(v.Get("a")), b(v.Has("b")), len(v["a"]), len(v["zz"]))
	v.Del("b")
	fmt.Println("values", q(v.Encode()), len(v), q(v.Get("a")), b(v.Has("b")), len(v["a"]), len(v["zz"]))
	v.Add("d", "")
	fmt.Println("values", q(v.Encode()), len(v), q(v.Get("a")), b(v.Has("b")), len(v["a"]), len(v["zz"]))
	v.Set("d", "z")
	fmt.Println("values", q(v.Encode()), len(v), q(v.Get("a")), b(v.Has("b")), len(v["a"]), len(v["zz"]))
	v.Add("e f", "g")
	fmt.Println("values", q(v.Encode()), len(v), q(v.Get("a")), b(v.Has("b")), len(v["a"]), len(v["zz"]))
}
