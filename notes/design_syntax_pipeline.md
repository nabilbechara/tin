# Edition-1 syntax pipeline interface

Status: proposed for #224. This is an internal compiler interface; spelling and semantics stay
as decided in `notes/design_syntax.md` and `notes/design_semantics.md`. The translator, parser,
and later semantic steps share this contract. No consumer should depend on it until every
Syntax pipeline member (#225, #226, #227, #228) approves the interface PR.

## Entry points

- `parse(toks)` remains the edition-0 entry point.
- `parse_edition1(toks)` is the edition-1 entry point selected by `-edition 1`. Both populate the
  same program tables for functions, constants, globals, types and shapes, so checking, lowering
  and code generation keep one input model.
- `print_edition1(file, source, toks)` prints one parsed file in canonical edition-1 syntax and
  returns its text. It takes the original source and tokens so it can preserve comments and blank
  lines without adding comment nodes to the checked tree. It does not run checking or lowering.
- Tokens retain their source position and leading trivia (spaces, line breaks and comments). The
  printer copies trivia at declaration and statement boundaries and formats rewritten syntax
  canonically. Unattached trailing trivia is copied at end of file.

## Node representation

Nodes keep the current packed-word layout: `N_KIND` at word 0, `N_POS` at word 1, and the existing
type and region slots. New kind numbers are appended after `TX_DYN`; numbers are stable and never
reused. Each kind's field offsets are declared beside its kind in `selfhost/parse.tin`. Vectors
preserve source order. A parser-only construct is normalized to an existing node only when that
preserves its bindings, evaluation order, source positions and formatting information.

The edition-1 nodes needed by the grammar have these payloads (word 2 onward):

| Node | Payload |
|---|---|
| `EX_MATCH` | subject expression; ordered vector of arms |
| match arm | vector of patterns; optional guard expression; expression or block body; source position |
| pattern | kind and source position, then literal/range endpoints, binding name, or variant name and child patterns |
| `EX_UNIT` | original numeric token text; unit kind (`ns`, `us`, `ms`, `s`, `m`, `h`, `b`, `kb`, `mb`, `gb`) |
| `EX_COALESCE` | optional expression; fallback expression |
| `EX_WRAP` | fallible expression; message expression |
| `EX_BOUNDARY` | boundary kind (`within`, `limit`, `guard`, `arena`, `parallel`, `with`); ordered argument expressions; body block |
| `ST_SELECT` | ordered vector of arms; each arm has optional binding name, wait expression, body, and source position |
| `ST_SCOPE` | scope name; body block |
| `ST_DETACH`, `ST_ONCE` | body block |
| `TX_SECRET` | inner type expression |
| `TX_MAX` | inner type expression; maximum expression |
| attribute | name; ordered argument expressions; source position |
| `ST_USE` | resource name; initializer expression |
| `ST_ON` | event expression; body block |

Attributes attach as ordered vectors to the declaration, function, or struct field they precede;
existing field slots are preserved (including the JSON field-name slot). `let`/`mut` mutability
is stored on the binding/declaration. `if let` uses the existing `ST_IF` initializer slot. The four
`for` forms use `ST_RANGE` or `ST_WHILE`; a label is an additional loop field. Keyed struct
literals keep using `EX_COMPOSITE` and `CL_KEYS`.

The semantic issue that owns a later construct may add fields only through its own interface PR;
it must preserve this common header, the edition-1 printer contract, and the node shapes above.
