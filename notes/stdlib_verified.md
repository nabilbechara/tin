# Stdlib verification against Go (bench/ref/NAME/main.go)

| package | Go reference | result |
|---|---|---|
| mint | strconv | identical on all cases |
| gauge | math, math/bits | identical except 1-ulp differences in transcendental functions (Tin uses Apple libm, Go its own; libm is the correctly rounded one where checkable) |
| tide | time | identical |
| dice | same algorithms in Go | identical |
| sift | slices/sort | identical |
| cairn | hand-written Go equivalents | identical |
| trail | path/filepath | identical |
| quarry | os | identical except stderr interleaving and naming fdopendir instead of open in one error |
| lever | flag | identical except: a value that fails to parse leaves the flag unchanged (Go overwrites it with a zero value) |
| twine, glyph | strings, unicode/utf8 | checked by hand against Go semantics |
