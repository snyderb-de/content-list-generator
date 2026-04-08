package main

import "sync"

var (
	activeScanMu      sync.Mutex
	activeScanCancel  func()
	activeScanTokenID uint64
)

func setActiveScanCancel(cancel func()) uint64 {
	activeScanMu.Lock()
	defer activeScanMu.Unlock()
	activeScanTokenID++
	activeScanCancel = cancel
	return activeScanTokenID
}

func clearActiveScanCancel(token uint64) {
	activeScanMu.Lock()
	defer activeScanMu.Unlock()
	if token == activeScanTokenID {
		activeScanCancel = nil
	}
}

func cancelActiveScan() bool {
	activeScanMu.Lock()
	cancel := activeScanCancel
	activeScanMu.Unlock()
	if cancel == nil {
		return false
	}
	cancel()
	return true
}
