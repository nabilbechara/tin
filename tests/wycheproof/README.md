# Wycheproof test vectors

Copied unchanged from [C2SP/wycheproof](https://github.com/C2SP/wycheproof) `testvectors_v1/`
at commit `3fa63dd0344abb611f1fb1d77e119938603ea230` (Apache License 2.0). They are run by
`tools/ci/crypto_check.py`, which feeds each test to `tools/ci/fixtures/crypto_vectors.tin`
and checks valid results byte for byte and that invalid inputs are rejected.
