//go:build !darwin && !windows

package main

import (
	"os"
	"time"
)

func fileCreationTime(os.FileInfo) (time.Time, bool) {
	return time.Time{}, false
}
