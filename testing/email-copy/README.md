# Email-Copy Testing

Files in this area support the email-copy workflow.

- `fixtures/` holds the tracked source tree and expected manifest fixture.
- `generate_fixture.py` rebuilds the fixture source and expected manifest deterministically.
- `run_checks.sh` runs the Go and Python email-copy test modules.
- `generated/` is ignored and available for scratch outputs while comparing runs.
