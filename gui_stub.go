//go:build !gui

package main

import "fmt"

func launchGUI(_ string) error {
	return fmt.Errorf("Go GUI is available in gui-tagged builds. Run with: go run -tags gui . --gui")
}
