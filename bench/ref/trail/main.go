// Reference for tests/v2/trail.tin: prints the same lines with Go's path/filepath.
package main

import (
	"fmt"
	"path/filepath"
)

func e(err error) string {
	if err == nil {
		return "<nil>"
	}
	return err.Error()
}

func main() {
	cleans := []string{"abc", "abc/def", "a/b/c", ".", "..", "../..", "../../abc", "/abc", "/", "", "abc/", "abc/def/", "a/b/c/", "./", "../", "../../", "/abc/", "abc//def//ghi", "//abc", "///abc", "//abc//", "abc//", "abc/./def", "/./abc/def", "abc/.", "abc/def/..", "abc/def/../..", "abc/def/../../..", "/abc/def/../../..", "abc/def/../../../ghi/jkl/../../../mno", "/../abc", "a/../b:/../../c", "abc/./../def", "abc//./../def", "abc/../../././../def", "/..", "/../..", "./././a", "a/./././", "héllo/../wörld/./ß", "...", "a/.../b", "/a/b/c/../../../../d"}
	for _, p := range cleans {
		fmt.Println("clean", fmt.Sprintf("%q -> %q", p, filepath.Clean(p)))
	}

	bases := []string{"", ".", "/.", "/", "////", "x/", "abc", "abc/def", "a/b/.x", "a/b/c.", "a/b/c.x", "a//b//", "..", "/a/..", "ß/é"}
	for _, p := range bases {
		d, f := filepath.Split(p)
		fmt.Println("base dir split", fmt.Sprintf("%q -> %q %q | %q %q", p, filepath.Base(p), filepath.Dir(p), d, f))
	}

	dirs := []string{"", ".", "/.", "/", "////", "/foo", "x/", "abc", "abc/def", "a/b/.x", "a/b/c.", "a/b/c.x", "a/b/../c", "/a/b/../../.."}
	for _, p := range dirs {
		fmt.Println("dir", fmt.Sprintf("%q -> %q", p, filepath.Dir(p)))
	}

	exts := []string{"path.go", "path.pb.go", "a.dir/b", "a.dir/b.go", "a.dir/", ".", "..", ".bashrc", "a/.b.c", "noext", "", "/x.y/z", "trailing."}
	for _, p := range exts {
		fmt.Println("ext", fmt.Sprintf("%q -> %q", p, filepath.Ext(p)))
	}

	abss := []string{"", "/", "/usr/bin/gcc", "..", "/a/../bb", ".", "./", "lala", "//"}
	for _, p := range abss {
		fmt.Println("isabs", fmt.Sprintf("%q", p), filepath.IsAbs(p))
	}

	joinA := []string{"a", "a", "", "/", "/", "/", "//", "/a", "a/", "a/", "", "a/b", "", "..", "x", "/", "a"}
	joinB := []string{"b", "", "b", "a", "a/b", "", "a", "b", "b", "", "", "../../../xyz", "/abs", "..", "./y/", "/", "/b"}
	for i, x := range joinA {
		fmt.Println("join2", fmt.Sprintf("%q %q -> %q", x, joinB[i], filepath.Join(x, joinB[i])))
	}
	fmt.Println("join3", fmt.Sprintf("%q %q %q %q", filepath.Join("/", "a", "b"), filepath.Join("a", "", "b"), filepath.Join("", "", ""), filepath.Join("a", "..", "c")))
	fmt.Println("joinall", fmt.Sprintf("%q %q %q %q %q", filepath.Join(), filepath.Join(""), filepath.Join("", "", "x", "", "y/"), filepath.Join("/", "", "a", "b", "..", "c"), filepath.Join("a")))

	relBase := []string{"a/b", "a/b/.", "a/b", "./a/b", "a/b", "ab/cd", "ab/cd", "a/b", "a/b", "a/b/../c", "a/b/c", "a/b", "a/b/c/d", "a/b/c/d", "a/b/c/d/", "a/b/c/d/", "../../a/b", "/a/b", "/a/b/.", "/a/b", "/ab/cd", "/ab/cd", "/a/b", "/a/b", "/a/b/../c", "/a/b/c", "/a/b", "/a/b/c/d", "/a/b/c/d", "/a/b/c/d/", "/a/b/c/d/", "/../../a/b", ".", ".", "..", "..", "../..", "a", "/a", "", "/", "/", "a/b", "é/ß"}
	relTarg := []string{"a/b", "a/b", "a/b/.", "a/b", "./a/b", "ab/cde", "ab/c", "a/b/c/d", "a/b/../c", "a/b", "a/c/d", "c/d", "a/b", "a/b/", "a/b", "a/b/", "../../a/b/c/d", "/a/b", "/a/b", "/a/b/.", "/ab/cde", "/ab/c", "/a/b/c/d", "/a/b/../c", "/a/b", "/a/c/d", "/c/d", "/a/b", "/a/b/", "/a/b", "/a/b/", "/../../a/b/c/d", "a/b", "..", ".", "a", "..", "/a", "a", "x/y", "/", "/x", "/a/b", "é/x"}
	for i, bp := range relBase {
		r, err := filepath.Rel(bp, relTarg[i])
		fmt.Println("rel", fmt.Sprintf("%q %q -> %q", bp, relTarg[i], r), e(err))
	}

	pats := []string{"abc", "*", "*c", "a*", "a*", "a*", "a*/b", "a*/b", "a*b*c*d*e*/f", "a*b*c*d*e*/f", "a*b*c*d*e*/f", "a*b*c*d*e*/f", "a*b?c*x", "a*b?c*x", "ab[c]", "ab[b-d]", "ab[e-g]", "ab[^c]", "ab[^b-d]", "ab[^e-g]", "a\\*b", "a\\*b", "a?b", "a[^a]b", "a???b", "a[^a][^a][^a]b", "[a-ζ]*", "*[a-ζ]", "a?b", "a*b", "[\\]a]", "[\\-]", "[x\\-]", "[x\\-]", "[x\\-]", "[\\-x]", "[\\-x]", "[\\-x]", "[]a]", "[-]", "[x-]", "[x-]", "[x-]", "[-x]", "[-x]", "[-x]", "\\", "[a-b-c]", "[", "[^", "[^bc", "a[", "a[", "a[", "a/b[", "*x", "", "", "*", "**", "a**b", "?", "?", "*/*", "*/*", "[[:alpha:]]", "x[a-]", "a\\", "*.go", "*.go", "[abc", "ab*[", "*[", "a*[]", "a??"}
	names := []string{"abc", "abc", "abc", "a", "abc", "ab/c", "abc/b", "a/c/b", "axbxcxdxe/f", "axbxcxdxexxx/f", "axbxcxdxe/xxx/f", "axbxcxdxexxx/fff", "abxbbxdbxebxczzx", "abxbbxdbxebxczzy", "abc", "abc", "abc", "abc", "abc", "abc", "a*b", "ab", "a☺b", "a☺b", "a☺b", "a☺b", "α", "A", "a/b", "a/b", "]", "-", "x", "-", "z", "x", "-", "a", "]", "-", "x", "-", "z", "x", "-", "a", "a", "a", "a", "a", "a", "a", "ab", "x", "x", "xxx", "", "a", "", "abc", "ab", "a", "/", "a/b", "a/b/c", "a", "a", "a", "main.go", "dir/main.go", "a", "abx", "x", "a", "a☺"}
	for i, p := range pats {
		m, err := filepath.Match(p, names[i])
		fmt.Println("match", fmt.Sprintf("%q %q", p, names[i]), m, e(err))
	}
}
