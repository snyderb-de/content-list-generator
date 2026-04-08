package main

import (
	"sync/atomic"
	"time"
)

type progressPhase string

const (
	progressPhaseIdle     progressPhase = "idle"
	progressPhaseCounting progressPhase = "counting"
	progressPhaseScanning progressPhase = "scanning"
	progressPhaseXLSX     progressPhase = "xlsx"
)

type globalProgress struct {
	phase            progressPhase
	files            uint64
	directories      uint64
	bytes            uint64
	filtered         uint64
	totalFiles       uint64
	totalDirectories uint64
	totalBytes       uint64
	currentItem      string
	startedAt        time.Time
	phaseStartedAt   time.Time
}

var scanProgressState atomic.Value

func currentProgress() globalProgress {
	if value := scanProgressState.Load(); value != nil {
		return value.(globalProgress)
	}
	now := time.Now()
	return globalProgress{
		phase:          progressPhaseIdle,
		startedAt:      now,
		phaseStartedAt: now,
	}
}

func setProgress(progress globalProgress) {
	scanProgressState.Store(progress)
}

func progressFraction(progress globalProgress) float64 {
	if progress.phase != progressPhaseScanning {
		return 0
	}
	if progress.totalBytes > 0 {
		value := float64(progress.bytes) / float64(progress.totalBytes)
		if value < 0 {
			return 0
		}
		if value > 1 {
			return 1
		}
		return value
	}
	if progress.totalFiles == 0 {
		return 0
	}
	value := float64(progress.files) / float64(progress.totalFiles)
	if value < 0 {
		return 0
	}
	if value > 1 {
		return 1
	}
	return value
}

func progressETA(progress globalProgress, now time.Time) time.Duration {
	if progress.phase != progressPhaseScanning {
		return 0
	}
	elapsed := now.Sub(progress.phaseStartedAt)
	if elapsed <= 0 {
		return 0
	}
	if progress.totalBytes > 0 && progress.bytes > 0 {
		remaining := progress.totalBytes - progress.bytes
		if remaining == 0 {
			return 0
		}
		return time.Duration(float64(elapsed) * (float64(remaining) / float64(progress.bytes)))
	}
	if progress.totalFiles == 0 || progress.files == 0 {
		return 0
	}
	remaining := progress.totalFiles - progress.files
	if remaining == 0 {
		return 0
	}
	return time.Duration(float64(elapsed) * (float64(remaining) / float64(progress.files)))
}

func progressPhaseLabel(phase progressPhase) string {
	switch phase {
	case progressPhaseCounting:
		return "Counting"
	case progressPhaseScanning:
		return "Scanning"
	case progressPhaseXLSX:
		return "Creating XLSX"
	default:
		return "Idle"
	}
}
