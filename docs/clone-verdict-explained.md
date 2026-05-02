# Clone Verdict — What Each Result Means

## Overview

A clone compare produces one of three verdicts. Each verdict is determined by the
two-pass comparison engine:

- **Pass 1** — streaming sorted merge: resolves files at identical paths
- **Pass 2** — hash cross-reference: resolves path-only files by content fingerprint

The verdict reflects content integrity, not folder structure.

---

## ✓ Exact Clone

**Definition:** Every file on Drive A exists on Drive B at the exact same path, with
the same hash value. No files are missing, added, moved, or renamed.

**Conditions:**
- Zero hash mismatches
- Zero missing files (no match)
- Zero extra files (no match)
- Zero moved/renamed files
- Zero duplicates

**Operational meaning:** The drives are identical. Either drive can serve as a
replacement for the other without any reconciliation step.

**Archival / legal context:** An Exact Clone is the strongest form of verification.
It demonstrates that the clone was produced correctly and that no content has changed
on either drive since cloning. Suitable for chain-of-custody handoff, court submission,
or long-term archival deposit where path structure is part of the record.

---

## ~ Content Clone

**Definition:** Every file on Drive A is present on Drive B by content (hash match),
but one or more files appear at different paths — due to a folder rename, reorganization,
or mount-point difference.

**Conditions:**
- Zero hash mismatches
- Zero missing files (no match)
- Zero extra files (no match)
- One or more moved/renamed files
- Duplicates on either drive are permitted

**Operational meaning:** All content is intact and verified present on both drives.
The structural difference (different folder names or paths) does not indicate data loss
or corruption. The drives hold the same files.

**Archival / legal context:** A Content Clone is sufficient for most archival purposes
where the goal is to preserve file content, not folder structure. The report documents
exactly which paths changed, providing a clear audit trail. If folder structure is
legally significant (e.g., the directory organization is itself evidence), note the
path differences explicitly in any handoff documentation.

**Common causes:**
- A top-level folder was renamed after cloning (e.g. `1971-2025` → `1971_2025`)
- Files were moved between subdirectories without changing content
- Drive letters or mount points differ between OS environments
- Backup software reorganized the folder hierarchy during copy

---

## ✗ Not a Clone

**Definition:** One or more files are genuinely unaccounted for. Either a file exists
on Drive A with no hash match anywhere on Drive B, or a file exists on Drive B with no
hash match anywhere on Drive A. Hash mismatches on matching paths also trigger this verdict.

**Conditions (any one is sufficient):**
- One or more files missing from Drive B with no hash match (alarming)
- One or more extra files on Drive B with no hash match (alarming)
- One or more hash mismatches on files at the same path

**Operational meaning:** The drives cannot be confirmed as equivalent. Investigation
is required before treating either drive as a verified copy of the other.

**Archival / legal context:** A Not a Clone result should not be dismissed as a
technicality. It means one or more files are unverified. The appropriate response
depends on the stakes:

- **Low stakes / working copy:** investigate the specific files flagged, confirm
  whether they are OS noise missed by the exclusion filter, then re-run after correction
- **High stakes / legal hold / court submission:** document the discrepancies in
  writing before proceeding. Do not overwrite either drive until the cause is understood.
  Consult legal counsel if chain of custody is in question.

**Common causes that require investigation:**
- Files deleted from one drive after cloning
- Files added to one drive after cloning
- Partial clone (copy was interrupted)
- Bit-rot or storage failure on one drive
- Files skipped during clone due to permissions or path length limits

**Common causes that are OS noise (re-run after exclusion confirms):**
- Windows shadow copy or VSS snapshots
- Application lock files created during scan
- Temp files written during scan (`.tmp`, `~$*`)

---

## Alarming vs. Non-Alarming Differences

Not all differences are equally serious. The report and diff CSV distinguish:

| Category | Alarming | Meaning |
|---|---|---|
| Missing from 2nd Drive (no match) | **Yes** | File on Drive A has no hash match anywhere on Drive B |
| Extra on 2nd Drive (no match) | **Yes** | File on Drive B has no hash match anywhere on Drive A |
| Hash mismatch (same path) | **Yes** | Same path, different content — possible corruption |
| Moved / renamed | No | Same content, different path — folder reorganization |
| Duplicate on 2nd Drive | No | Extra copy of a file that does exist on Drive A |
| Duplicate on 1st Drive | No | Extra copy on Drive A that has a match on Drive B |

Alarming differences are what produce a **Not a Clone** verdict. The diff CSV and
the UI surface these in a separate section so they are not buried in moved/renamed noise.

---

## Excluded System Paths

The tool automatically excludes OS infrastructure paths from all scans before comparison.
These paths are never archival content and always differ between drives:

**Windows:** `$RECYCLE.BIN/`, `System Volume Information/`, `pagefile.sys`,
`hiberfil.sys`, `swapfile.sys`, `Thumbs.db`, `desktop.ini`, `*.tmp`, `~$*`, `.~lock.*`

**macOS:** `.DS_Store`, `.Spotlight-V100/`, `.Trashes/`, `.fseventsd/`,
`.TemporaryItems/`, `.DocumentRevisions-V100/`, `._*`

The report shows how many paths were excluded from each drive so the exclusion is
auditable.

---

## Real Example — City of Newark Drives (2026-04-30 / 2026-05-02)

**Drives:** CON-P74THY (Drive A) and CON-M4EM1V (Drive B)  
**Content:** 1,836 PDFs spanning 1971–2025  
**Verdict:** Not a Clone

| Category | Count |
|---|---|
| Exact path + content matches | 5 |
| Moved / renamed | 0 |
| Missing (no match) | 1,831 |
| Extra (no match) | 1,831 |
| Hash mismatches | 0 |
| System paths excluded | 4 |

**What we found:** 1,831 files have the same filename and the same byte size on
both drives, but different hash values. The only path difference is a folder
rename: `ALD-004_Docket_Books_Digital_Scans_1971-2025` (Drive A) vs
`ALD-004_Docket_Books_Digital_Scans_1971_2025` (Drive B).

Binary inspection of five representative files confirmed the cause.

---

### PDF Document ID Analysis

Every PDF file embeds a pair of document IDs in its cross-reference trailer —
an MD5 fingerprint generated at export time. These IDs differ between the two
drives across all 1,831 mismatched files, while the remaining content is
byte-identical.

**Example 1 — `Fri Apr 01 00_00_00 EDT 2016-0.pdf` (14,764,233 bytes)**
```
Drive A ID: <4906b42ce32684a02a88a3e8da3c55ff> <254c0903233b0999e56bbe47c3f3a99b>
Drive B ID: <50d4888a236d02a073281bfe9ae1d225> <06fb995a7b2eea3b937ddb1d88c0772b>
Bytes differing: 67 of 14,764,233 — all within last 804 bytes (trailer only)
```

**Example 2 — `Fri Apr 01 00_00_00 EDT 2022-0.pdf` (32,771,102 bytes)**
```
Drive A ID: <3c4bb51fc6d2e5952c2e54af759319b2> <0a4e61c457e895d775fc7d02da689f10>
Drive B ID: <3fe7d20dd0fe02e81dd81a27712c94bc> <3e866ada98f291acc1087d4a76180e33>
```

**Example 3 — `Fri Apr 04 00_00_00 EDT 2014-0.pdf` (21,040,330 bytes)**
```
Drive A ID: <929ffe6af003694e90eeb46d793f2384> <4b641f73d7b91b6ec41825794b55b2c5>
Drive B ID: <f17748542e5722b2eb99ed0d1650c9ec> <0ecf44becd68225f75b3a2c40af7f79b>
```

**Example 4 — `Fri Apr 04 00_00_00 EDT 2025-0.pdf` (9,680,388 bytes)**
```
Drive A ID: <b73bcf25054114c255a43b26de3fb0a1> <25f2eea866feecf23b75d55bc716eb9f>
Drive B ID: <776c986eaabcc846df55a3ebb0408a48> <b712403bfbd17ba60a41b6dbfcef5e46>
```

**Example 5 — `Fri Apr 05 00_00_00 EDT 2013-0.pdf` (12,477,823 bytes)**
```
Drive A ID: <67ec738d0293009a292435d28e0f33d5> <dc490b7c3892e7d16aa67e573ca364ce>
Drive B ID: <afdb9991d5ed5c25bba38c4e9cdbcb09> <868a9c6616beccab3ab5f1627e76467b>
```

In every case: same file name, same byte size, same visible content — but both
document IDs differ. The differences are confined to the last ~800 bytes of
each file (the PDF cross-reference trailer). The preceding 14–32 MB are
byte-for-byte identical.

---

### What this means

The two drives were **not cloned from each other**. The 1,836 PDFs were
independently exported twice from the same source — a scanner, PDF converter,
or document management system. Each export run generates fresh document IDs
even when producing bit-identical visible content.

**Technically:** `Not a Clone` — the binary files differ, and hash verification
correctly flags them. This is the right answer.

**Operationally:** The visible records are present on both drives. The
difference is a PDF metadata artifact, not a content difference. Both drives
represent complete transfers of the same archival material.

**Legally:** Document for the record that the two drives were independently
produced rather than one being a copy of the other. If chain of custody
requires bit-identical copies, one drive should be re-cloned from the other.
If the goal is only to confirm both drives hold the same records, a soft
compare (ignoring PDF document IDs) can verify this — see Phase 7 of the
tool's development roadmap.

---

### Note on the earlier analysis (April 2026)

The initial investigation using the path-only engine concluded these were
"content clones" because it could not compare hashes across renamed paths.
That conclusion was incorrect. The two-pass hash engine (Phase 2) revealed
the true result: independent exports, not a clone relationship.
