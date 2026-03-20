package main

import (
	"encoding/csv"
	"os"
	"path/filepath"
	"testing"
)

func TestRunScanWritesCSVAndHashes(t *testing.T) {
	workspace := t.TempDir()
	source := filepath.Join(workspace, "source")
	if err := os.MkdirAll(filepath.Join(source, "nested"), 0o755); err != nil {
		t.Fatalf("mkdir source: %v", err)
	}
	if err := os.WriteFile(filepath.Join(source, "a.txt"), []byte("hello\n"), 0o644); err != nil {
		t.Fatalf("write a.txt: %v", err)
	}
	if err := os.WriteFile(filepath.Join(source, "nested", "b.bin"), []byte("1234567890"), 0o644); err != nil {
		t.Fatalf("write b.bin: %v", err)
	}

	output := filepath.Join(workspace, "report.csv")
	done, err := runScan(source, output, scanOptions{
		Hashing:       true,
		IncludeHidden: true,
		IncludeSystem: true,
		ExcludedExts:  map[string]struct{}{},
	})
	if err != nil {
		t.Fatalf("runScan failed: %v", err)
	}
	if done.files != 2 {
		t.Fatalf("expected 2 files, got %d", done.files)
	}
	if done.hashWorkers < 2 {
		t.Fatalf("expected parallel hash workers when hashing is enabled, got %d", done.hashWorkers)
	}

	file, err := os.Open(output)
	if err != nil {
		t.Fatalf("open output: %v", err)
	}
	defer file.Close()

	rows, err := csv.NewReader(file).ReadAll()
	if err != nil {
		t.Fatalf("read csv: %v", err)
	}
	if len(rows) != 3 {
		t.Fatalf("expected 3 rows, got %d", len(rows))
	}
	if rows[1][0] != "a.txt" {
		t.Fatalf("expected first data row to be a.txt, got %q", rows[1][0])
	}
	if rows[2][4] != "nested/b.bin" {
		t.Fatalf("expected nested relative path, got %q", rows[2][4])
	}
	if rows[1][5] == "" || rows[2][5] == "" {
		t.Fatalf("expected hashes to be written")
	}
}

func TestRunScanAppliesFilters(t *testing.T) {
	workspace := t.TempDir()
	source := filepath.Join(workspace, "source")
	if err := os.MkdirAll(filepath.Join(source, ".hidden"), 0o755); err != nil {
		t.Fatalf("mkdir hidden source: %v", err)
	}
	if err := os.WriteFile(filepath.Join(source, ".hidden", "secret.txt"), []byte("secret"), 0o644); err != nil {
		t.Fatalf("write hidden file: %v", err)
	}
	if err := os.WriteFile(filepath.Join(source, "visible.log"), []byte("log"), 0o644); err != nil {
		t.Fatalf("write visible.log: %v", err)
	}
	if err := os.WriteFile(filepath.Join(source, "Thumbs.db"), []byte("thumbs"), 0o644); err != nil {
		t.Fatalf("write Thumbs.db: %v", err)
	}
	if err := os.WriteFile(filepath.Join(source, "keep.txt"), []byte("keep"), 0o644); err != nil {
		t.Fatalf("write keep.txt: %v", err)
	}

	output := filepath.Join(workspace, "filtered.csv")
	done, err := runScan(source, output, scanOptions{
		Hashing:       false,
		IncludeHidden: false,
		IncludeSystem: false,
		ExcludedExts: map[string]struct{}{
			"log": {},
		},
	})
	if err != nil {
		t.Fatalf("runScan failed: %v", err)
	}
	if done.files != 1 {
		t.Fatalf("expected 1 kept file, got %d", done.files)
	}
	if done.filtered != 3 {
		t.Fatalf("expected 3 filtered files/directories, got %d", done.filtered)
	}

	file, err := os.Open(output)
	if err != nil {
		t.Fatalf("open output: %v", err)
	}
	defer file.Close()

	rows, err := csv.NewReader(file).ReadAll()
	if err != nil {
		t.Fatalf("read csv: %v", err)
	}
	if len(rows) != 2 {
		t.Fatalf("expected header plus one row, got %d rows", len(rows))
	}
	if rows[1][0] != "keep.txt" {
		t.Fatalf("expected keep.txt to remain, got %q", rows[1][0])
	}
}
