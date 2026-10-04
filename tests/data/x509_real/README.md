Public root certificates that `tools/ci/x509_check.py` byte-flips besides the test PKI and the
system bundle, because each once showed a parser difference from Go's `crypto/x509`:

- `harica-root-2011.pem`: Hellenic Academic and Research Institutions RootCA 2011, from the
  macOS (LibreSSL 3.3.6) bundle. Its name constraints permit email domains; Tin did not check
  that those values are ASCII.
