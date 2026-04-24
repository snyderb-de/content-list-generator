package main

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/xuri/excelize/v2"
)

func TestRunScanWritesCSVAndHashes(t *testing.T) {
	workspace := t.TempDir()
	source := filepath.Join(workspace, "source")
	if err := ensureDir(filepath.Join(source, "nested")); err != nil {
		t.Fatalf("mkdir source: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, "a.txt"), "hello\n"); err != nil {
		t.Fatalf("write a.txt: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, "nested", "b.bin"), "1234567890"); err != nil {
		t.Fatalf("write b.bin: %v", err)
	}

	output := filepath.Join(workspace, "report.csv")
	done, err := runScan(source, output, scanOptions{
		HashAlgorithm: hashAlgorithmSHA256,
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
	if filepath.Base(done.outputPath) != "report-001.csv" {
		t.Fatalf("expected first output part to be report-001.csv, got %s", filepath.Base(done.outputPath))
	}
	if done.hashWorkers < 2 {
		t.Fatalf("expected parallel hash workers when hashing is enabled, got %d", done.hashWorkers)
	}
	if done.reportPath == "" {
		t.Fatalf("expected report path to be set")
	}
	reportBytes, err := os.ReadFile(done.reportPath)
	if err != nil {
		t.Fatalf("read report: %v", err)
	}
	reportText := string(reportBytes)
	if !strings.Contains(reportText, "Selected folder: source") {
		t.Fatalf("expected report to include selected folder name, got %q", reportText)
	}
	if !strings.Contains(reportText, "First file in CSV: a.txt") || !strings.Contains(reportText, "Last file in CSV: nested/b.bin") {
		t.Fatalf("expected report to include first/last csv items, got %q", reportText)
	}

	rows := readCSVRows(t, done.outputPath)
	if len(rows) != 3 {
		t.Fatalf("expected 3 rows, got %d", len(rows))
	}
	if rows[1][0] != "a.txt" {
		t.Fatalf("expected first data row to be a.txt, got %q", rows[1][0])
	}
	if rows[2][4] != "nested/b.bin" {
		t.Fatalf("expected nested relative path, got %q", rows[2][4])
	}
	if rows[1][5] != "SHA-256" || rows[2][5] != "SHA-256" {
		t.Fatalf("expected hash algorithm column to be populated")
	}
	if rows[1][6] == "" || rows[2][6] == "" {
		t.Fatalf("expected hashes to be written")
	}
}

func TestRunScanAppliesFilters(t *testing.T) {
	workspace := t.TempDir()
	source := filepath.Join(workspace, "source")
	if err := ensureDir(filepath.Join(source, ".hidden")); err != nil {
		t.Fatalf("mkdir hidden source: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, ".hidden", "secret.txt"), "secret"); err != nil {
		t.Fatalf("write hidden file: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, "visible.log"), "log"); err != nil {
		t.Fatalf("write visible.log: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, "Thumbs.db"), "thumbs"); err != nil {
		t.Fatalf("write Thumbs.db: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, "keep.txt"), "keep"); err != nil {
		t.Fatalf("write keep.txt: %v", err)
	}

	output := filepath.Join(workspace, "filtered.csv")
	done, err := runScan(source, output, scanOptions{
		HashAlgorithm: hashAlgorithmOff,
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

	rows := readCSVRows(t, done.outputPath)
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
	if err := ensureDir(source); err != nil {
		t.Fatalf("mkdir source: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, "report.txt"), "hello"); err != nil {
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

func TestRunScanDeletesCSVAfterXLSXWhenEnabled(t *testing.T) {
	workspace := t.TempDir()
	source := filepath.Join(workspace, "source")
	if err := ensureDir(source); err != nil {
		t.Fatalf("mkdir source: %v", err)
	}
	if err := writeFixtureFile(filepath.Join(source, "keep.txt"), "hello"); err != nil {
		t.Fatalf("write keep.txt: %v", err)
	}

	output := filepath.Join(workspace, "report.csv")
	done, err := runScan(source, output, scanOptions{
		CreateXLSX:    true,
		PreserveZeros: true,
		DeleteCSV:     true,
		ExcludedExts:  map[string]struct{}{},
	})
	if err != nil {
		t.Fatalf("runScan failed: %v", err)
	}
	if !done.csvDeleted {
		t.Fatalf("expected csvDeleted to be true")
	}
	if _, err := os.Stat(done.outputPath); !os.IsNotExist(err) {
		t.Fatalf("expected csv output to be removed, got err=%v", err)
	}
	if done.xlsxPath == "" {
		t.Fatalf("expected xlsx path to be set")
	}
	if _, err := os.Stat(done.xlsxPath); err != nil {
		t.Fatalf("expected xlsx file to exist: %v", err)
	}
}

func TestRunScanSplitsCSVAndConvertsAllParts(t *testing.T) {
	workspace := t.TempDir()
	source := filepath.Join(workspace, "source")
	if err := ensureDir(source); err != nil {
		t.Fatalf("mkdir source: %v", err)
	}
	for index := 1; index <= 5; index++ {
		name := filepath.Join(source, fmt.Sprintf("file-%d.txt", index))
		if err := writeFixtureFile(name, fmt.Sprintf("value-%d", index)); err != nil {
			t.Fatalf("write fixture file %d: %v", index, err)
		}
	}

	output := filepath.Join(workspace, "report.csv")
	done, err := runScan(source, output, scanOptions{
		CreateXLSX:    true,
		PreserveZeros: true,
		DeleteCSV:     true,
		MaxRowsPerCSV: 2,
		ExcludedExts:  map[string]struct{}{},
	})
	if err != nil {
		t.Fatalf("runScan failed: %v", err)
	}
	if done.csvPartCount != 3 {
		t.Fatalf("expected 3 csv parts, got %d", done.csvPartCount)
	}
	if done.xlsxPartCount != 3 {
		t.Fatalf("expected 3 xlsx parts, got %d", done.xlsxPartCount)
	}
	if !done.csvDeleted {
		t.Fatalf("expected csv parts to be deleted after xlsx conversion")
	}
	if done.maxRowsPerCSV != 2 {
		t.Fatalf("expected max rows per csv to be 2, got %d", done.maxRowsPerCSV)
	}
	if len(done.outputPaths) != 3 || len(done.xlsxPaths) != 3 {
		t.Fatalf("expected three output and xlsx paths, got %d and %d", len(done.outputPaths), len(done.xlsxPaths))
	}
	for _, csvPath := range done.outputPaths {
		if _, err := os.Stat(csvPath); !os.IsNotExist(err) {
			t.Fatalf("expected csv part to be removed: %s (err=%v)", csvPath, err)
		}
	}
	for _, xlsxPath := range done.xlsxPaths {
		if _, err := os.Stat(xlsxPath); err != nil {
			t.Fatalf("expected xlsx part to exist: %s (err=%v)", xlsxPath, err)
		}
	}
}

func TestConvertCSVToXLSXPreservesLeadingZeros(t *testing.T) {
	workspace := t.TempDir()
	csvPath := filepath.Join(workspace, "input.csv")
	xlsxPath := filepath.Join(workspace, "output.xlsx")

	if err := os.WriteFile(csvPath, []byte(
		"File Name,Extension,Size in Bytes,Size in Human Readable,Path From Root Folder,Hash Algorithm,Hash Value\n"+
			"sample.txt,txt,00123,123 B,nested/sample.txt,,\n",
	), 0o644); err != nil {
		t.Fatalf("write csv: %v", err)
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

func TestRunScanMatchesGoldenFixture(t *testing.T) {
	workspace := t.TempDir()
	output := filepath.Join(workspace, "report.csv")
	source := filepath.Join("testing", "content-scan", "fixtures", "source")

	done, err := runScan(source, output, scanOptions{
		HashAlgorithm: hashAlgorithmSHA256,
		ExcludeHidden: true,
		ExcludeSystem: true,
		ExcludedExts: map[string]struct{}{
			"log": {},
		},
	})
	if err != nil {
		t.Fatalf("runScan failed: %v", err)
	}
	if done.files != 5 || done.filtered != 3 {
		t.Fatalf("unexpected counts: files=%d filtered=%d", done.files, done.filtered)
	}

	actualRows := readCSVRows(t, done.outputPath)
	expectedRows := readCSVRows(t, filepath.Join("testing", "content-scan", "fixtures", "expected-scan-hash.csv"))
	assertRowsEqual(t, actualRows, expectedRows)
}

func ensureDir(path string) error {
	return os.MkdirAll(path, 0o755)
}

func writeFixtureFile(path, content string) error {
	return os.WriteFile(path, []byte(content), 0o644)
}
