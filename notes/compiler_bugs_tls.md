# Compiler bugs found by the TLS server work (#124)

## A function type ending in a bare `!` swallows the end of its line

A global (or local) whose type is a function type with a result of only `!` cannot end its line
there: the parser reads on into the next line for a result type.

```tin
package main

mut h fn(i64) !
mut k i64

fn main() {}
```

gives `E020 UNEXPECTED: expected a name, found 'mut'` at the second declaration. In a parameter
list (`body fn(i64) !, r i64`) it parses, because a comma follows. Workaround: write the empty
result as `!()` (`mut h fn(i64) !()`), which is the same type: lib/anvil/serve_tls.tin does this
for `gTlsWrite`.
