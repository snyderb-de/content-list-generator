package main

import (
	"encoding/csv"
	"os"
	"path/filepath"
	"testing"

	"github.com/xuri/excelize/v2"
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
		ExcludeHidden: false,
		ExcludeSystem: false,
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
		ExcludeHidden: true,
		ExcludeSystem: true,
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

func TestRunScanCreatesXLSX(t *testing.T) {
	workspace := t.TempDir()
	source := filepath.Join(workspace, "source")
	if err := os.MkdirAll(source, 0o755); err != nil {
		t.Fatalf("mkdir source: %v", err)
	}
	if err := os.WriteFile(filepath.Join(source, "report.txt"), []byte("hello"), 0o644); err != nil {
		t.Fatalf("write report.txt: %v", err)
	}

	output := filepath.Join(workspace, "report.csv")
	done, err := runScan(source, output, scanOptions{
		CreateXLSX:    true,
		PreserveZeros: true,
		ExcludedExts:  map[string]struct{}{},
	})
	if err != nil {
		t.Fatalf("runScan failed: %v", err)
	}
	if done.xlsxPath == "" {
		t.Fatalf("expected xlsx path to be set")
	}
	if _, err := os.Stat(done.xlsxPath); err != nil {
		t.Fatalf("expected xlsx file to exist: %v", err)
	}

	book, err := excelize.OpenFile(done.xlsxPath)
	if err != nil {
		t.Fatalf("open xlsx: %v", err)
	}
	defer book.Close()

	value, err := book.GetCellValue("Sheet1", "A2")
	if err != nil {
		t.Fatalf("read xlsx cell: %v", err)
	}
	if value != "report.txt" {
		t.Fatalf("expected xlsx to contain report.txt, got %q", value)
	}
}

func TestConvertCSVToXLSXPreservesLeadingZeros(t *testing.T) {
	workspace := t.TempDir()
	csvPath := filepath.Join(workspace, "input.csv")
	xlsxPath := filepath.Join(workspace, "output.xlsx")

	file, err := os.Create(csvPath)
	if err != nil {
		t.Fatalf("create csv: %v", err)
	}
	writer := csv.NewWriter(file)
	if err := writer.Write([]string{
		"File Name",
		"Extension",
		"Size in Bytes",
		"Size in Human Readable",
		"Path From Root Folder",
		"SHA256 Hash",
	}); err != nil {
		t.Fatalf("write header: %v", err)
	}
	if err := writer.Write([]string{"sample.txt", "txt", "00123", "123 B", "nested/sample.txt", ""}); err != nil {
		t.Fatalf("write row: %v", err)
	}
	writer.Flush()
	if err := writer.Error(); err != nil {
		t.Fatalf("flush csv: %v", err)
	}
	if err := file.Close(); err != nil {
		t.Fatalf("close csv: %v", err)
	}

	if err := convertCSVToXLSX(csvPath, xlsxPath, true); err != nil {
		t.Fatalf("convert csv to xlsx: %v", err)
	}

	book, err := excelize.OpenFile(xlsxPath)
	if err != nil {
		t.Fatalf("open xlsx: %v", err)
	}
	defer book.Close()

	value, err := book.GetCellValue("Sheet1", "C2")
	if err != nil {
		t.Fatalf("read xlsx cell: %v", err)
	}
	if value != "00123" {
		t.Fatalf("expected leading zeros to be preserved, got %q", value)
	}
}

func TestCopyEmailFilesPreservesStructureAndWritesManifest(t *testing.T) {
	workspace := t.TempDir()
	source := filepath.Join(workspace, "source")
	dest := filepath.Join(workspace, "dest")
	if err := os.MkdirAll(filepath.Join(source, "Inbox", "nested"), 0o755); err != nil {
		t.Fatalf("mkdir source: %v", err)
	}
	if err := os.WriteFile(filepath.Join(source, "Inbox", "mail.eml"), []byte("message"), 0o644); err != nil {
		t.Fatalf("write mail.eml: %v", err)
	}
	if err := os.WriteFile(filepath.Join(source, "Inbox", "nested", "archive.pst"), []byte("archive"), 0o644); err != nil {
		t.Fatalf("write archive.pst: %v", err)
	}
	if err := os.WriteFile(filepath.Join(source, "Inbox", "ignore.txt"), []byte("ignore"), 0o644); err != nil {
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

	manifestFile, err := os.Open(manifestPath)
	if err != nil {
		t.Fatalf("open manifest: %v", err)
	}
	defer manifestFile.Close()

	rows, err := csv.NewReader(manifestFile).ReadAll()
	if err != nil {
		t.Fatalf("read manifest: %v", err)
	}
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
