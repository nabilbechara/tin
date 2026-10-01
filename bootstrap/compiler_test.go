package main

import (
	"bytes"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
)

// Tests run against stage 0 in-process, or against the self-hosted compiler named
// by $TINC. With TINC_ASM=1 the self-hosted compiler prints assembly (-S) and cc
// links it; otherwise it writes the executable itself.

func runTinc(args ...string) (string, error) {
	var stdout, stderr bytes.Buffer
	cmd := exec.Command(os.Getenv("TINC"), args...)
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("%v: %s", err, stderr.String())
	}
	return stdout.String(), nil
}

// build compiles files into the executable exe.
func build(files []string, exe string) error {
	var asm string
	var err error
	switch {
	case os.Getenv("TINC") == "":
		asm, err = CompileFiles(files)
	case os.Getenv("TINC_ASM") == "1":
		asm, err = runTinc(append([]string{"-S"}, files...)...)
	default:
		_, err = runTinc(append([]string{"-o", exe}, files...)...)
		return err
	}
	if err != nil {
		return err
	}
	return Assemble(asm, exe)
}

// expectations reads `// expect: LINE` (stdout lines) and `// exit: N` comments.
func expectations(src string) (string, int) {
	var out strings.Builder
	exit := 0
	for _, line := range strings.Split(src, "\n") {
		if i := strings.Index(line, "// expect:"); i >= 0 {
			out.WriteString(strings.TrimPrefix(line[i+len("// expect:"):], " "))
			out.WriteByte('\n')
		}
		if i := strings.Index(line, "// exit: "); i >= 0 {
			exit, _ = strconv.Atoi(strings.TrimSpace(line[i+len("// exit: "):]))
		}
	}
	return out.String(), exit
}

func TestPrograms(t *testing.T) {
	paths, _ := filepath.Glob("../tests/*.tin")
	if len(paths) == 0 {
		t.Fatal("no test programs found")
	}
	for _, path := range paths {
		t.Run(filepath.Base(path), func(t *testing.T) {
			t.Parallel()
			src, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			wantOut, wantExit := expectations(string(src))
			exe := filepath.Join(t.TempDir(), "prog")
			if err := build([]string{"../lib/std.tin", path}, exe); err != nil {
				t.Fatalf("build: %v", err)
			}
			out, err := exec.Command(exe).Output()
			gotExit := 0
			var exitErr *exec.ExitError
			if errors.As(err, &exitErr) {
				gotExit = exitErr.ExitCode()
			} else if err != nil {
				t.Fatal(err)
			}
			if string(out) != wantOut {
				t.Errorf("stdout mismatch\n--- got ---\n%s--- want ---\n%s", out, wantOut)
			}
			if gotExit != wantExit {
				t.Errorf("exit code %d, want %d", gotExit, wantExit)
			}
		})
	}
}

func TestErrors(t *testing.T) {
	paths, _ := filepath.Glob("../tests/errors/*.tin")
	for _, path := range paths {
		t.Run(filepath.Base(path), func(t *testing.T) {
			t.Parallel()
			src, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			first, _, _ := strings.Cut(string(src), "\n")
			want, ok := strings.CutPrefix(first, "// error: ")
			if !ok {
				t.Fatal("first line must be `// error: MESSAGE`")
			}
			err = build([]string{"../lib/std.tin", path}, filepath.Join(t.TempDir(), "prog"))
			if err == nil {
				t.Fatalf("compiled successfully, want error containing %q", want)
			}
			if !strings.Contains(err.Error(), want) {
				t.Errorf("error %q does not contain %q", err, want)
			}
		})
	}
}
