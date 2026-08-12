//go:build windows

package main

import (
	"os"
	"syscall"
	"time"
)

func fileCreationTime(info os.FileInfo) (time.Time, bool) {
	data, ok := info.Sys().(*syscall.Win32FileAttributeData)
	if !ok {
		return time.Time{}, false
	}
	nanoseconds := data.CreationTime.Nanoseconds()
	if nanoseconds <= 0 {
		return time.Time{}, false
	}
	return time.Unix(0, nanoseconds), true
}
