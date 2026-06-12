package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestCopyEmailFilesPreservesStructureAndWritesManifest(t *testing.T) {
	workspace := t.TempDir()
	source := filepath.Join(workspace, "source")
	dest := filepath.Join(workspace, "dest")
	if err := ensureDir(filepath.Join(source, "Inbox", "nested")); err != nil {
		t.Fatalf("mkdir source: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, "Inbox", "mail.eml"), "message"); err != nil {
		t.Fatalf("write mail.eml: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, "Inbox", "nested", "archive.pst"), "archive"); err != nil {
		t.Fatalf("write archive.pst: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, "Inbox", "ignore.txt"), "ignore"); err != nil {
		t.Fatalf("write ignore.txt: %v", err)
	}

	manifestPath, copied, err := copyEmailFiles(source, dest)
	if err != nil {
		t.Fatalf("copyEmailFiles failed: %v", err)
	}
	if copied != 2 {
		t.Fatalf("expected 2 copied files, got %d", copied)
	}

	for _, relative := range []string{"Inbox/mail.eml", "Inbox/nested/archive.pst"} {
		if _, err := os.Stat(filepath.Join(dest, relative)); err != nil {
			t.Fatalf("expected copied file %s: %v", relative, err)
		}
	}

	rows := readCSVRows(t, manifestPath)
	if len(rows) != 3 {
		t.Fatalf("expected header plus 2 rows, got %d", len(rows))
	}
	if rows[1][2] != "Inbox/mail.eml" {
		t.Fatalf("expected relative path in manifest, got %q", rows[1][2])
	}
	if rows[2][4] != ".pst" {
		t.Fatalf("expected extension .pst, got %q", rows[2][4])
	}
}

func TestCopyEmailFilesRejectsNestedDestination(t *testing.T) {
	workspace := t.TempDir()
	source := filepath.Join(workspace, "source")
	dest := filepath.Join(source, "copied-emails")
	if err := ensureDir(source); err != nil {
		t.Fatalf("mkdir source: %v", err)
	}

	if _, _, err := copyEmailFiles(source, dest); err == nil {
		t.Fatalf("expected nested destination to be rejected")
	}
}

func TestCopyEmailFilesIncludesOlk15Message(t *testing.T) {
	workspace := t.TempDir()
	source := filepath.Join(workspace, "source")
	dest := filepath.Join(workspace, "dest")
	if err := ensureDir(filepath.Join(source, "Inbox")); err != nil {
		t.Fatalf("mkdir source: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, "Inbox", "note.olk15Message"), "olk"); err != nil {
		t.Fatalf("write olk15Message: %v", err)
	}

	manifestPath, copied, err := copyEmailFiles(source, dest)
	if err != nil {
		t.Fatalf("copyEmailFiles failed: %v", err)
	}
	if copied != 1 {
		t.Fatalf("expected 1 copied file, got %d", copied)
	}
	if _, err := os.Stat(filepath.Join(dest, "Inbox", "note.olk15Message")); err != nil {
		t.Fatalf("expected .olk15Message file to be copied: %v", err)
	}
	if _, err := os.Stat(manifestPath); err != nil {
		t.Fatalf("expected manifest to exist: %v", err)
	}
}

func TestCopyEmailFilesMatchesGoldenFixture(t *testing.T) {
	workspace := t.TempDir()
	source := filepath.Join("testing", "email-copy", "fixtures", "source")
	dest := filepath.Join(workspace, "emails")

	manifestPath, copied, err := copyEmailFiles(source, dest)
	if err != nil {
		t.Fatalf("copyEmailFiles failed: %v", err)
	}

	type expectedManifest struct {
		Copied int                 `json:"copied"`
		Rows   []map[string]string `json:"rows"`
	}
	var expected expectedManifest
	raw, err := os.ReadFile(filepath.Join("testing", "email-copy", "fixtures", "expected-email-manifest.json"))
	if err != nil {
		t.Fatalf("read expected manifest: %v", err)
	}
	if err := json.Unmarshal(raw, &expected); err != nil {
		t.Fatalf("unmarshal expected manifest: %v", err)
	}
	if int(copied) != expected.Copied {
		t.Fatalf("expected %d copied files, got %d", expected.Copied, copied)
	}

	rows := readCSVRows(t, manifestPath)
	if len(rows) != len(expected.Rows)+1 {
		t.Fatalf("expected %d rows including header, got %d", len(expected.Rows)+1, len(rows))
	}
	for index, expectedRow := range expected.Rows {
		actual := map[string]string{
			"Relative Path": rows[index+1][2],
			"File Name":     rows[index+1][3],
			"Extension":     rows[index+1][4],
			"Size in Bytes": rows[index+1][5],
		}
		if actual["Relative Path"] == "" || actual["File Name"] == "" {
			t.Fatalf("expected populated manifest row at index %d", index)
		}
		for key, expectedValue := range expectedRow {
			if actual[key] != expectedValue {
				t.Fatalf("row %d field %s mismatch: got %q want %q", index, key, actual[key], expectedValue)
			}
		}
		if _, err := os.Stat(filepath.Join(dest, actual["Relative Path"])); err != nil {
			t.Fatalf("expected copied file %s: %v", actual["Relative Path"], err)
		}
	}
}
