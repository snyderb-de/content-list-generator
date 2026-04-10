# Content-Scan Testing

Files in this area support the content-list workflow.

- `fixtures/` holds the tracked golden fixture source tree and expected CSV.
- `generate_fixture.py` rebuilds the fixture source and expected output deterministically.
- `run_checks.sh` runs the Go and Python content-scan test modules.
- `generated/` is ignored and available for scratch outputs while comparing runs.
