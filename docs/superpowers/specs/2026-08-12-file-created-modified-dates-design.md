# File Creation and Modification Dates

## Goal

Add filesystem creation and modification timestamps to the standard content-list output. This gives the client both dates without changing specialized output formats.

## Output Schema

Append these columns after `Hash Value` in the standard CSV and generated XLSX output:

1. `Date Created`
2. `Date Modified`

Timestamp values use the local timezone of the machine performing the scan and this format:

```text
YYYY-MM-DD HH:MM:SS ±HH:MM
```

Example:

```text
2026-08-12 15:42:07 -04:00
```

If a timestamp is unavailable, the field contains `unknown`.

## Timestamp Semantics

- `Date Created` is the filesystem creation or birth timestamp when the operating system and filesystem expose one.
  - Windows uses the native file creation timestamp.
  - macOS uses the filesystem birth timestamp.
  - Linux and unsupported filesystems use `unknown` when no birth timestamp is available.
- `Date Modified` is the filesystem last-modified timestamp.
- Copying, restoring, downloading, or migrating a file can change its filesystem creation timestamp. The value is metadata reported at scan time, not proof of the date the document's contents were authored.

## Scope

The new columns apply only to the standard content-list output.

The following schemas remain unchanged:

- Agency-template output
- Folders-only output
- Email-copy manifest
- Clone-difference output

Clone comparison remains compatible with new standard content lists because the columns are appended after the existing seven fields. Existing parsing continues to use the original column positions.

## Architecture and Data Flow

### Go runtime

The scanner already retrieves file metadata before creating each work item. Extend the work item with formatted creation and modification values. Use small platform-specific helpers for creation time so OS-specific filesystem structures remain isolated from the scan pipeline. Format valid timestamps through one shared formatter and write `unknown` for unavailable values.

Append the two values to standard report rows. Agency-template rows continue through their existing independent row builder and do not receive the new values.

### Python runtime

The Python scanner already calls `Path.stat()` while enumerating files. Carry the resulting timestamp metadata into row generation rather than performing a separate filesystem lookup. Read the platform's birth or creation field when available, use the Windows creation-time behavior where applicable, and otherwise emit `unknown`. Format modification time using the same output contract as Go.

Append the two values only to standard report rows.

### XLSX generation

No separate schema implementation is required. XLSX generation converts the completed CSV and therefore inherits both appended columns and their string values.

## Error Handling

Failure to retrieve a creation timestamp does not fail or skip a scan. The field is written as `unknown`.

The existing scan behavior for a complete file metadata lookup failure remains unchanged. Formatting helpers must not panic or raise for missing, invalid, or out-of-range timestamp values; they return `unknown`.

## Compatibility

- Existing seven standard columns retain their names, order, and values.
- New columns are appended, avoiding index shifts in clone comparison.
- Agency-template consumers receive exactly their current schema.
- Go and Python outputs use identical column names, order, timestamp format, and fallback value.

## Testing

Add or update tests to verify:

- Standard Go output contains both new headers and formatted values.
- Standard Python output contains both new headers and formatted values.
- Missing creation metadata produces `unknown` without failing the scan.
- Go/Python parity checks validate the same headers, ordering, formatter, and fallback behavior.
- Agency-template headers and row widths are unchanged.
- Clone comparison accepts standard scan CSVs containing the appended fields.
- CSV-to-XLSX conversion preserves both columns as strings.

Before each fixture scan, assign the source files a fixed modification time so `Date Modified` can be compared with a deterministic golden value. Creation time cannot be assigned portably, so fixture assertions validate that `Date Created` is either a correctly formatted native timestamp or `unknown`; they do not hard-code a machine-specific creation time. Dedicated platform-neutral unit tests cover the shared formatter and unavailable-value fallback.

## Documentation

Update the user manual's standard CSV column reference with both fields, the timestamp format, the `unknown` fallback, and the caveat that file copying can alter creation metadata.
