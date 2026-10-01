// Command tinc0 is the stage-0 Tin compiler, written in Go.
package main

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

const usage = `usage:
  tinc0 asm   FILE.tin...                 print ARM64 assembly to stdout
  tinc0 build [-o OUT] FILE.tin...        compile to a native executable (default a.out)
  tinc0 run   FILE.tin... [-- ARGS...]    compile and run`

func main() {
	if len(os.Args) < 3 {
		fmt.Fprintln(os.Stderr, usage)
		os.Exit(2)
	}
	cmd, args := os.Args[1], os.Args[2:]
	var err error
	switch cmd {
	case "asm":
		err = cmdAsm(args)
	case "build":
		err = cmdBuild(args)
	case "run":
		err = cmdRun(args)
	default:
		fmt.Fprintln(os.Stderr, usage)
		os.Exit(2)
	}
	if err != nil {
		var exit *exec.ExitError
		if errors.As(err, &exit) {
			os.Exit(exit.ExitCode())
		}
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

// CompileFiles runs the whole pipeline: lex and parse each file, check, generate assembly.
func CompileFiles(paths []string) (string, error) {
	if len(paths) == 0 {
		return "", errors.New("no input files")
	}
	prog := &Program{}
	for _, path := range paths {
		src, err := os.ReadFile(path)
		if err != nil {
			return "", err
		}
		toks, err := Lex(path, src)
		if err != nil {
			return "", err
		}
		if err := Parse(toks, prog); err != nil {
			return "", err
		}
	}
	if err := Check(prog); err != nil {
		return "", err
	}
	return Generate(prog)
}

// Assemble links assembly into an executable with the system C toolchain.
func Assemble(asm, out string) error {
	dir, err := os.MkdirTemp("", "tinc")
	if err != nil {
		return err
	}
	defer os.RemoveAll(dir)
	sPath := filepath.Join(dir, "out.s")
	if err := os.WriteFile(sPath, []byte(asm), 0o644); err != nil {
		return err
	}
	cc := exec.Command("cc", "-o", out, sPath)
	if msg, err := cc.CombinedOutput(); err != nil {
		return fmt.Errorf("cc failed: %v\n%s", err, msg)
	}
	return nil
}

func cmdAsm(files []string) error {
	asm, err := CompileFiles(files)
	if err != nil {
		return err
	}
	_, err = os.Stdout.WriteString(asm)
	return err
}

func cmdBuild(args []string) error {
	out := "a.out"
	if len(args) >= 2 && args[0] == "-o" {
		out, args = args[1], args[2:]
	}
	asm, err := CompileFiles(args)
	if err != nil {
		return err
	}
	return Assemble(asm, out)
}

func cmdRun(args []string) error {
	files, progArgs := args, []string(nil)
	for i, a := range args {
		if a == "--" {
			files, progArgs = args[:i], args[i+1:]
			break
		}
	}
	asm, err := CompileFiles(files)
	if err != nil {
		return err
	}
	dir, err := os.MkdirTemp("", "tinrun")
	if err != nil {
		return err
	}
	defer os.RemoveAll(dir)
	exe := filepath.Join(dir, "prog")
	if err := Assemble(asm, exe); err != nil {
		return err
	}
	run := exec.Command(exe, progArgs...)
	run.Stdin, run.Stdout, run.Stderr = os.Stdin, os.Stdout, os.Stderr
	return run.Run()
}
