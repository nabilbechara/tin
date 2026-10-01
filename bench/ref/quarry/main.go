// Reference for tests/v2/quarry.tin: prints the same lines with Go's os package.
package main

import (
	"fmt"
	"os"
	"path/filepath"
)

func e(err error) string {
	if err == nil {
		return "<nil>"
	}
	return err.Error()
}

func exists(p string) bool {
	_, err := os.Stat(p)
	return err == nil
}

func isDir(p string) bool {
	fi, err := os.Stat(p)
	return err == nil && fi.IsDir()
}

func size(p string) (int64, error) {
	fi, err := os.Stat(p)
	if err != nil {
		return 0, err
	}
	return fi.Size(), nil
}

func modTime(p string) (int64, error) {
	fi, err := os.Stat(p)
	if err != nil {
		return 0, err
	}
	return fi.ModTime().Unix(), nil
}

func appendFile(p, data string) error {
	f, err := os.OpenFile(p, os.O_WRONLY|os.O_CREATE|os.O_APPEND, 0644)
	if err != nil {
		return err
	}
	_, err = f.WriteString(data)
	if err1 := f.Close(); err1 != nil && err == nil {
		err = err1
	}
	return err
}

func readDir(p string) ([]string, error) {
	ents, err := os.ReadDir(p)
	names := []string{}
	for _, d := range ents {
		names = append(names, d.Name())
	}
	return names, err
}

func readFile(p string) (string, error) {
	b, err := os.ReadFile(p)
	return string(b), err
}

func main() {
	a := os.Args
	fmt.Println("args", len(a) >= 1, len(a[0]) > 0)

	fmt.Println("env set", e(os.Setenv("QUARRY_T", "v1")), fmt.Sprintf("%q", os.Getenv("QUARRY_T")))
	v, ok := os.LookupEnv("QUARRY_T")
	fmt.Println("env lookup", fmt.Sprintf("%q", v), ok)
	fmt.Println("env set empty", e(os.Setenv("QUARRY_T", "")), fmt.Sprintf("%q", os.Getenv("QUARRY_T")))
	v, ok = os.LookupEnv("QUARRY_T")
	fmt.Println("env lookup empty", fmt.Sprintf("%q", v), ok)
	fmt.Println("env unset", e(os.Unsetenv("QUARRY_T")))
	v, ok = os.LookupEnv("QUARRY_T")
	fmt.Println("env lookup unset", fmt.Sprintf("%q", v), ok)
	fmt.Println("env bad key", e(os.Setenv("", "x")), e(os.Setenv("A=B", "x")), e(os.Setenv("A\x00B", "x")))
	fmt.Println("env empty key", fmt.Sprintf("%q", os.Getenv("")))
	fmt.Println("env unicode", e(os.Setenv("QUARRY_U", "héllo €")), os.Getenv("QUARRY_U"))
	v, ok = os.LookupEnv("QUARRY_NEVER_SET_XYZ")
	fmt.Println("env missing", fmt.Sprintf("%q", v), ok)

	tmp := filepath.Join(os.TempDir(), "quarry_test_dir")
	fmt.Println("tempdir abs", filepath.IsAbs(os.TempDir()))
	fmt.Println("setup", e(os.RemoveAll(tmp)), e(os.MkdirAll(tmp, 0755)), e(os.Chdir(tmp)))
	wd, err := os.Getwd()
	fmt.Println("getwd", e(err), filepath.Base(wd))
	fmt.Println("getwd set pwd", e(os.Setenv("PWD", tmp)))
	wd, err = os.Getwd()
	fmt.Println("getwd via pwd", e(err), wd == tmp)

	fmt.Println("mkdirall", e(os.MkdirAll("d1/d2/d3", 0755)), isDir("d1/d2"), exists("d1/d2/d3"), e(os.MkdirAll("d1/d2/d3", 0755)), e(os.MkdirAll("d1/d2/d3/", 0755)))
	fmt.Println("mkdir exists", e(os.Mkdir("d1", 0755)))
	fmt.Println("mkdir no parent", e(os.Mkdir("nope/x", 0755)))
	fmt.Println("write", e(os.WriteFile("f.txt", []byte("hello\n"), 0644)))
	s, err := readFile("f.txt")
	fmt.Println("read", fmt.Sprintf("%q", s), e(err))
	n, err := size("f.txt")
	fmt.Println("size", n, e(err))
	fmt.Println("append", e(appendFile("f.txt", "wörld")))
	s, err = readFile("f.txt")
	fmt.Println("read appended", fmt.Sprintf("%q", s), e(err))
	n, err = size("f.txt")
	fmt.Println("size appended", n, e(err))
	fmt.Println("overwrite", e(os.WriteFile("f.txt", []byte("x"), 0644)))
	n, err = size("f.txt")
	fmt.Println("size overwritten", n, e(err))
	fmt.Println("write empty", e(os.WriteFile("empty", []byte(""), 0644)), exists("empty"), isDir("empty"))
	s, err = readFile("empty")
	fmt.Println("read empty", fmt.Sprintf("%q", s), e(err), len(s))
	n, err = size("empty")
	fmt.Println("size empty", n, e(err))
	fmt.Println("append creates", e(appendFile("app.txt", "a")), e(appendFile("app.txt", "b")))
	s, err = readFile("app.txt")
	fmt.Println("read app", s, e(err))
	fmt.Println("mkdirall over file", e(os.MkdirAll("f.txt", 0755)), e(os.MkdirAll("f.txt/sub", 0755)))
	_, err = readFile("missing")
	fmt.Println("read missing", e(err))
	_, err = readFile("d1")
	fmt.Println("read dir", e(err))
	fmt.Println("write dir", e(os.WriteFile("d1", []byte("x"), 0644)))
	fmt.Println("write no parent", e(os.WriteFile("nope/f", []byte("x"), 0644)))
	n, err = size("missing")
	fmt.Println("size missing", n, e(err))
	fmt.Println("exists missing", exists("missing"), isDir("missing"), isDir("f.txt"))

	b := make([]byte, 0, 1000000)
	for i := 0; i < 1000000; i++ {
		b = append(b, byte((i*7+i/1000)&255))
	}
	fmt.Println("write big", e(os.WriteFile("big.bin", b, 0644)))
	s, err = readFile("big.bin")
	sum := int64(0)
	for i := 0; i < len(s); i++ {
		sum += int64(s[i]) * int64(i%13+1)
	}
	fmt.Println("read big", len(s), e(err), sum)
	n, err = size("big.bin")
	fmt.Println("size big", n, e(err))
	mt, err := modTime("big.bin")
	fmt.Println("modtime", mt > 1600000000, e(err))
	_, err = modTime("missing")
	fmt.Println("modtime missing", e(err))

	fmt.Println("rename", e(os.Rename("f.txt", "g.txt")), exists("f.txt"), exists("g.txt"))
	fmt.Println("rename missing", e(os.Rename("missing", "h")))
	fmt.Println("rename onto dir", e(os.Rename("g.txt", "d1")))
	fmt.Println("rename dir onto dir", e(os.Rename("d1/d2", "d1")))
	fmt.Println("rename dir", e(os.Rename("d1/d2/d3", "d1/d3")), isDir("d1/d3"), exists("d1/d2/d3"))
	fmt.Println("rename over file", e(os.Rename("g.txt", "app.txt")), exists("g.txt"))
	s, err = readFile("app.txt")
	fmt.Println("read replaced", s, e(err))

	fmt.Println("remove nonempty", e(os.Remove("d1")))
	fmt.Println("remove missing", e(os.Remove("missing")))
	fmt.Println("remove", e(os.Remove("d1/d3")), e(os.Remove("app.txt")), exists("d1/d3"), exists("app.txt"))

	names, err := readDir(".")
	fmt.Println("readdir", names, e(err))
	_, err = readDir("missing")
	fmt.Println("readdir missing", e(err))
	_, err = readDir("empty")
	fmt.Println("readdir file", e(err))
	names, err = readDir("d1/d2")
	fmt.Println("readdir empty", len(names), e(err))
	fmt.Println("mkdir many", e(os.Mkdir("many", 0755)))
	for i := 0; i < 40; i++ {
		err = os.WriteFile(fmt.Sprintf("many/n%02d", (i*17)%40), []byte(""), 0644)
		if err != nil {
			fmt.Println("many write failed", e(err))
		}
	}
	extra := []string{"é", "Z", "a", ".hidden", "~", "0", "n1", "n100"}
	for _, x := range extra {
		err = os.WriteFile("many/"+x, []byte(x), 0644)
		if err != nil {
			fmt.Println("extra write failed", e(err))
		}
	}
	fmt.Println("mkdir nested", e(os.MkdirAll("many/sub/deep", 0755)), e(os.WriteFile("many/sub/deep/leaf", []byte("leaf"), 0644)))
	names, err = readDir("many")
	fmt.Println("readdir many", len(names), e(err), names[0], names[1], names[2], names[len(names)-1])
	fmt.Println("readdir many all", names)
	fmt.Println("removeall", e(os.RemoveAll("many")), exists("many"), e(os.RemoveAll("missing")), e(os.RemoveAll("d1")), exists("d1"))
	fmt.Println("removeall file", e(os.RemoveAll("empty")), exists("empty"))

	_, err = readFile("a\x00b")
	fmt.Println("nul path", fmt.Sprintf("%q", err.Error()))
	fmt.Println("chdir missing", e(os.Chdir("missing")))
	h, err := os.Hostname()
	fmt.Println("hostname", len(h) > 0, e(err))
	fmt.Println("pid", os.Getpid() > 0)

	fmt.Println("cleanup", e(os.Chdir("/")), e(os.RemoveAll(tmp)), exists(tmp))
	fmt.Fprint(os.Stderr, "quarry test: ")
	fmt.Fprintln(os.Stderr, "stderr works")
	fmt.Println("exit flushes")
	os.Exit(0)
}
