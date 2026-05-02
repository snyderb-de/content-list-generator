# Clone Verification — Investigation Guide

When a clone compare returns **Not a Clone**, the differences almost never mean the
files are corrupted. This guide walks through how to diagnose what actually happened.

For a full explanation of what each verdict means operationally and legally, see
[clone-verdict-explained.md](clone-verdict-explained.md).

---

## Step 1 — Read the reports first

Each content list scan produces a `*-report.txt`. Compare them side by side before
touching the CSVs.

| Field | What to compare |
|---|---|
| **Files included** | Should be equal or very close |
| **Folders counted** | Should be equal |
| **Total size** | Should be identical to the byte |
| **Top extensions** | Same extensions, same sizes? |
| **Items skipped** | Hidden/system files excluded? Counts differ? |

If total size matches but file counts differ → paths changed (rename, move).
If total size differs → files added, removed, or corrupted.

---

## Step 2 — Count the differences by category

Open the two CSVs. Extract the path column and diff them:

```bash
# macOS / Linux
tail -n +2 DRIVE-A.csv | cut -d',' -f5 | sort > /tmp/paths_a.txt
tail -n +2 DRIVE-B.csv | cut -d',' -f5 | sort > /tmp/paths_b.txt

echo "Only on Drive A:"
comm -23 /tmp/paths_a.txt /tmp/paths_b.txt | wc -l

echo "Only on Drive B:"
comm -13 /tmp/paths_a.txt /tmp/paths_b.txt | wc -l

echo "In common:"
comm -12 /tmp/paths_a.txt /tmp/paths_b.txt | wc -l
```

If "only on A" and "only on B" counts are similar and large → likely a **folder rename**
(same files, different path prefix). See Step 4.

---

## Step 3 — Check for hash mismatches on common paths

Files that exist on both drives but have different content:

```python
import csv, sys

def load(path):
    m = {}
    with open(path, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            p = row['Path From Root Folder'].strip()
            m[p] = (row['Hash Value'].strip(), row['Size in Bytes'].strip())
    return m

a = load('DRIVE-A.csv')
b = load('DRIVE-B.csv')

common = set(a) & set(b)
mismatches = [(p, a[p], b[p]) for p in common if a[p][0] != b[p][0]]
print(f"Hash mismatches on {len(common)} common paths: {len(mismatches)}")
for p, av, bv in mismatches:
    print(f"  {p}")
    print(f"    A: {av[0][:20]}… {av[1]} bytes")
    print(f"    B: {bv[0][:20]}… {bv[1]} bytes")
```

---

## Step 4 — Diagnose the diff pattern

### Pattern: large symmetric diff (A missing N files, B missing N files, same file names)

**Cause: folder rename.**
One folder was renamed after cloning. Every file inside appears missing from both sides.

How to confirm:
```bash
comm -23 /tmp/paths_a.txt /tmp/paths_b.txt | head -5
comm -13 /tmp/paths_a.txt /tmp/paths_b.txt | head -5
```
If the paths look the same except for one segment, it's a rename.

**Fix:** Rename the folder on one drive to match the other, then re-run the clone check.

---

### Pattern: files only on one side, no mirror on the other

**Cause: files added or deleted after cloning.**

Check file dates if possible. Common culprits:
- Work continued on one drive after cloning
- A temp file or log was created
- Files were moved out of the scanned folder

**Fix:** Determine which drive is the "correct" one and copy missing files across, or
accept the difference as intentional.

---

### Pattern: same path, hash mismatch, same size

**Cause: file modified in place** (rare for PDFs, common for logs, DBs, config files).

Check if the file is something that self-modifies:
- Database files (`.db`, `.sqlite`)
- Log files
- Thumbnail caches

**Fix:** If it's user content, investigate which version is correct. If it's a
self-modifying system file, exclude it from future scans.

---

### Pattern: hash mismatch on `System Volume Information/*`

**Expected. Not a real difference.**

These files are Windows-internal and unique per drive:
- `IndexerVolumeGuid` — drive's unique ID, always different
- `WPSettings.dat` — Windows Portable settings, drive-specific
- `Tracking.log` — NTFS change journal fragments

**Fix:** Exclude `System Volume Information/` from content list scans, or ignore these
paths in the diff report.

---

### Pattern: files only on one side under `$RECYCLE.BIN/`

**Cause: files were deleted on one drive after cloning.**

The recycle bin holds files deleted but not permanently purged. These are not content
files.

**Fix:** Permanently empty the recycle bin on both drives before running a clone check,
or exclude `$RECYCLE.BIN/` from scans.

---

## Step 5 — Verify system exclusions ran

Since version 1.1, the tool automatically excludes all OS infrastructure paths before
comparison. No manual exclusion step is needed. The report shows how many paths were
excluded from each drive under **System paths excluded**.

Paths excluded automatically:

| Path | Platform |
|---|---|
| `$RECYCLE.BIN/`, `System Volume Information/` | Windows |
| `pagefile.sys`, `hiberfil.sys`, `swapfile.sys` | Windows |
| `Thumbs.db`, `desktop.ini`, `*.tmp`, `~$*`, `.~lock.*` | Windows |
| `.DS_Store`, `._*` | macOS |
| `.Spotlight-V100/`, `.Trashes/`, `.fseventsd/` | macOS |
| `.TemporaryItems/`, `.DocumentRevisions-V100/` | macOS |

If a **Not a Clone** verdict persists after confirming these were excluded, the
remaining differences require investigation — they are not OS noise.

---

## Common outcomes

| Verdict | What you see | Meaning | Action |
|---|---|---|---|
| Content Clone | Moved/renamed > 0, missing/extra = 0 | Folder renamed or reorganized after clone | No action — all content verified |
| Not a Clone | Missing (no match) > 0 | Files on Drive A absent from Drive B entirely | Investigate — missing content |
| Not a Clone | Extra (no match) > 0 | Files on Drive B absent from Drive A entirely | Investigate — unexpected content |
| Not a Clone | Hash mismatches > 0 | Same path, different content | Investigate — possible corruption |
| Exact Clone | All zeros | Perfect byte-identical copy | Done |

---

## Real example — City of Newark drives (2026-04-30)

**Drives:** CON-P74THY (Drive A) and CON-M4EM1V (Drive B)  
**Verdict:** Content Clone  
**Content:** 1,835 PDFs spanning 1971–2025

| Category | Count |
|---|---|
| Exact path + content matches | 2 |
| Moved / renamed (folder `1971-2025` → `1971_2025`) | 1,836 |
| Missing (no match) | 0 |
| Extra (no match) | 0 |
| Hash mismatches | 0 |
| System paths excluded (recycle bin, `System Volume Information`) | 4 |

**Explanation:** A top-level folder rename caused all 1,836 paths to appear missing
under a path-only diff. The two-pass hash engine matched them by content fingerprint
and classified them as moved/renamed. No files are missing or corrupted.

See [clone-verdict-explained.md](clone-verdict-explained.md) for full breakdown of this example.
