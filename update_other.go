//go:build !windows

package main

import "errors"

func readExecutableVersion(string) (string, error) {
	return "", errors.New("Windows executable version metadata is only available on Windows")
}

func verifyExecutableSignature(string, string) error {
	return errors.New("Windows executable signature verification is only available on Windows")
}

func launchPreparedUpdate(preparedUpdate, int) error {
	return errors.New("Windows executable updates are only available on Windows")
}
