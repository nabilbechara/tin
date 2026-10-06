# Tin for Visual Studio Code

Highlights `.tin` files, provides edition-1 snippets, and invokes the real compiler
for builds, runs, checks and tests. No compiler is bundled. No telemetry or network
access is used by the extension.

## Install

Install `tin-language-0.2.2.vsix` using **Extensions: Install from VSIX…**.
Open a saved `.tin` file. Set **Tin: Toolchain Root** to your Tin checkout or installation
(for example `/path/to/tin`), containing `bin/tinc` and `lib/`. Build/install the compiler
using Tin's normal installation instructions first.

When editing the Tin repository itself, `bin/tinc` is detected automatically.
Otherwise set `tin.compilerPath` to a `tinc` executable on PATH or an absolute path.
Use **tinc**, not the `tin` shell wrapper. A configured root is passed as `TIN_ROOT`;
without one, the compiler's own library discovery applies. Relative settings paths
resolve from the workspace. The extension runs on the workspace host, including
Linux through VS Code Remote SSH, WSL or Dev Containers.

## Commands

- **Tin: Build** writes `.tin-build/<first-file>-<target>` in the workspace.
- **Tin: Run** compiles for the native host and executes in the task terminal, with stdin.
- **Tin: Check (Compile Only)** fully compiles to a temporary executable, then deletes it.
- **Tin: Test Current Package** compiles all `.tin` files next to the active file with a generated
  crucible runner. Tests use one-line `fn TestXxx(t mut crucible.T) {` declarations
  (`func` in edition 0). Benchmarks are not run. Wrong signatures fail explicitly.

Compiler errors appear in the Problems panel. Failed compilation never runs a previous
executable. Compiler and program exit codes propagate to the task. Temporary outputs
are removed when tasks finish. Stop services with the task terminal's terminate action.
Commands save open source files before compiling. Tasks invoked through `tasks.json`
compile files already saved on disk. Compiler execution requires workspace trust.

Use **Tasks: Run Build Task** or **Tasks: Run Task** for detected tasks. Persist a task:

```json
{
  "version": "2.0.0",
  "tasks": [{"type": "tin", "action": "build", "file": "main.tin", "problemMatcher": "$tin"}]
}
```

## Settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `tin.compilerPath` | auto | Executable path or command name for `tinc` |
| `tin.toolchainRoot` | auto | Tin installation root / `TIN_ROOT` |
| `tin.edition` | `"1"` | New syntax, or `"0"` for existing Go-like syntax |
| `tin.target` | `"native"` | Build/check target: native, linux-arm64, linux-amd64, darwin-arm64 |
| `tin.entryFiles` | `[]` | Explicit workspace-relative inputs; otherwise active file |
| `tin.outputDirectory` | `".tin-build"` | Build output directory |
| `tin.runArguments` | `[]` | Arguments passed directly to the program |
| `tin.liveSyntaxChecks` | `true` | Compiler checks for unsaved edits, including type errors |
| `tin.checkOnSave` | `true` | Compiler checks on save |
| `tin.checkDelay` | `250` | Typing pause before a live check, in milliseconds |

Run and Test always compile for the native host, regardless of deployment build target.
Linux arm64 and Linux amd64 are production targets; macOS arm64 is for development.
Windows users should run the compiler in a Linux WSL/remote workspace.
Add `.tin-build/` to your project's `.gitignore`.

## Language status

The grammar covers the vision in `design/design_syntax.md`, including `with`, `within`,
unit literals, `secret`, bounded types and interpolation. The installed compiler decides
which features compile. For example, a `with` snippet requires policy support and an
actual policy supplied by your program/library. Highlighting does not imply implementation.

Compiler diagnostics now run on unsaved buffers as well as on open/save. Checks use a
private linked snapshot of the project and open buffers, so local imports remain available
without saving edits or changing your source files. Checks never execute the program.
The status bar shows checking, error counts, or toolchain failures. Click it for check logs.
Disable live checks with `tin.liveSyntaxChecks` and save checks with `tin.checkOnSave`;
`tin.checkDelay` controls the typing pause (default 250 ms).

Editing features include:

- Contextual completions for local declarations, declared receiver fields/methods, imported
  exported symbols and compiler builtins such as `say.Line`.
- Function signature help, declaration/documentation hovers, go-to-definition and outline symbols. Command-click an import path or package qualifier to open its source; relative file imports and vendored packages follow compiler resolution order.
- Quick fixes for split unit literals, return inside a boundary, and likely misspelled local names.
- Format Document for indentation, with multiline raw-string contents preserved.
- Run/Build links above `main`, package-test links above tests, and Ctrl+F5 to run.

Completions and navigation use a tolerant declaration index, not a complete compiler language
server. Declared and simple inferred types work; complex expression inference, cross-package
refactoring, rename and debugging are not implemented. Colors follow your selected VS Code theme.
Compiler support for the language vision remains independent from editor support.

## Develop and verify

Requires Node.js 20.19+ and npm. In `editors/vscode`:

```sh
npm ci
npm test
npm run test:host
npm run package
```

Tests cover TextMate tokenization, compiler arguments, test discovery, execution failures
and cleanup. Set `TIN_VSCODE_COMPILER=/absolute/path/to/bin/tinc` and
`TIN_ROOT=/absolute/path/to/tin` to also exercise native edition-1 compilation, runs,
errors and crucible tests. `test:host` downloads a VS Code test host and checks activation
and task execution in that host. Set `TIN_VSCODE_EXECUTABLE` to use an already-installed
VS Code executable instead of downloading one.

The `Tin VS Code extension` workflow runs on published releases and manual dispatch,
with native compiler integration tests and packaging on Linux arm64, Linux amd64
and macOS arm64. It does not run on PRs or ordinary pushes. The desktop host test
can be run locally.
