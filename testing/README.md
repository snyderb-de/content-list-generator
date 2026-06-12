# Testing

The repository now groups test support by feature instead of mixing everything into one shared folder.

- `testing/content-scan/` holds content-list fixtures, a fixture generator, and a feature-level runner.
- `testing/email-copy/` holds email-copy fixtures, a fixture generator, and a feature-level runner.
- `testing/manual-samples/` is for local real-world sample sets and stays ignored.
- `testing/manual-output/` is for local generated outputs and stays ignored.

Automated language-specific tests live close to the code:

- Go tests stay at the repo root in `*_test.go`.
- Python tests live in `python/tests/`.

The tracked fixture folders under `testing/` are the source of truth for cross-language parity checks.
