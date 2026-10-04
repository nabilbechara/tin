# Wycheproof test vectors

Copied unchanged from [C2SP/wycheproof](https://github.com/C2SP/wycheproof) `testvectors_v1/`
at commit `3fa63dd0344abb611f1fb1d77e119938603ea230` (Apache License 2.0). They are run by
`tools/ci/crypto_check.py`, which feeds each test to `tools/ci/fixtures/crypto_vectors.tin`
and checks valid results byte for byte and that invalid inputs are rejected.

`rsa/` and `ecdsa/` hold the RSA PKCS #1 v1.5 and PSS signature files (SHA-256/384/512) and
the ECDSA P-256 and P-384 files (DER signatures) from the same commit in a compact form, one line per key group and per test, written by
`tools/gen_wycheproof.py` (only the fields the tests use). `tests/v2/seal_wycheproof.tin` runs
them; its Go twin `bench/ref/seal_wycheproof` must print the same lines
(`tools/ci/x509_check.py`).
