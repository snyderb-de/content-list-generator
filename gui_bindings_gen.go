//go:build bindings

package main

import "os"

func init() {
	os.Args = append([]string{os.Args[0], "--gui"}, os.Args[1:]...)
}
