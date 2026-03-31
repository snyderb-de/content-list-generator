# Smoke Test Plan

This document gives a simple manual smoke test for:

- macOS
- Linux
- Windows

Use the same source folder on every OS:

```text
testdata/parity/source/
```

## Common Expected Results

Content-list scan settings:

- hashing on
- hidden files excluded
- system files excluded
- excluded extensions: `log`
- create XLSX on
- preserve leading zeros on

Expected kept files:

- `keep.txt`
- `mail/archive.pst`
- `mail/inbox.eml`
- `nested/0007.txt`
- `nested/data.bin`

Expected filtered items:

- `.hidden/secret.txt`
- `Thumbs.db`
- `skip.log`

Expected content-list output:

- one CSV
- one XLSX

Expected email-copy output:

- copied `mail/archive.pst`
- copied `mail/inbox.eml`
- one manifest CSV
- preserved `mail/` relative folder path in destination

## macOS

App to test:

- Go GUI

Launch:

```bash
./scripts/run_local.sh go-gui
```

Steps:

1. Open the Go GUI.
2. Select `testdata/parity/source/` as the source.
3. Choose an empty temp folder as the output location.
4. Run the content-list workflow with the common settings above.
5. Confirm the CSV and XLSX were created.
6. Open the XLSX and confirm the scan completed correctly.
7. Run the email-copy workflow.
8. Confirm the destination contains `mail/archive.pst` and `mail/inbox.eml`.
9. Open the manifest and confirm both rows exist.
10. Confirm the GUI open-result actions work.

## Linux

App to test:

- Go GUI

Launch:

```bash
./scripts/run_local.sh go-gui
```

Steps:

1. Open the Go GUI.
2. Repeat the same content-list workflow used on macOS.
3. Repeat the same email-copy workflow used on macOS.
4. Confirm output-opening actions work in the local desktop environment.
5. If the GUI cannot launch in the current Linux session, confirm the TUI fallback works with `./scripts/run_local.sh go`.

## Windows

App to test:

- Python GUI

Launch:

```bash
python .\python\content_list_generator.py
```

Steps:

1. Open the Python GUI.
2. Select `testdata/parity/source/` as the source.
3. Choose an empty temp folder as the output location.
4. Run the content-list workflow with the common settings above.
5. Confirm the CSV and XLSX were created.
6. Confirm the right-side latest-activity area updates.
7. Use the quick-open buttons for the latest CSV and XLSX.
8. Open the email-copy sub-window.
9. Copy into a fresh destination folder.
10. Confirm the manifest is created and the main window updates.
11. Use the quick-open manifest action.

## Pass / Fail

Pass if:

- the shipped GUI opens on that OS
- the app does not crash during the scan
- the app does not crash during email copy
- the expected files are produced
- the expected email files are copied
- the manifest is created
- recent-result open actions work

## Quick Automated Checks

Run before or after manual smoke testing:

```bash
./scripts/parity_check.sh
./scripts/dev_check.sh
```
