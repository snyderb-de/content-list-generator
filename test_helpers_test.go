package main

import (
	"encoding/csv"
	"os"
	"testing"
)

func readCSVRows(t *testing.T, path string) [][]string {
	t.Helper()
	file, err := os.Open(path)
	if err != nil {
		t.Fatalf("open csv %s: %v", path, err)
	}
	defer file.Close()

	rows, err := csv.NewReader(file).ReadAll()
	if err != nil {
		t.Fatalf("read csv %s: %v", path, err)
	}
	return rows
}

func assertRowsEqual(t *testing.T, actual, expected [][]string) {
	t.Helper()
	if len(actual) != len(expected) {
		t.Fatalf("row count mismatch: got %d want %d", len(actual), len(expected))
	}
	for rowIndex := range expected {
		if len(actual[rowIndex]) != len(expected[rowIndex]) {
			t.Fatalf("column count mismatch at row %d: got %d want %d", rowIndex, len(actual[rowIndex]), len(expected[rowIndex]))
		}
		for colIndex := range expected[rowIndex] {
			if actual[rowIndex][colIndex] != expected[rowIndex][colIndex] {
				t.Fatalf("cell mismatch at row %d col %d: got %q want %q", rowIndex, colIndex, actual[rowIndex][colIndex], expected[rowIndex][colIndex])
			}
		}
	}
}
