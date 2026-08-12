package main

import (
	"testing"
	"time"
)

func TestFormatFileTimestamp(t *testing.T) {
	previousLocal := time.Local
	time.Local = time.FixedZone("EDT", -4*60*60)
	t.Cleanup(func() { time.Local = previousLocal })
	value := time.Date(2026, 8, 12, 19, 42, 7, 900_000_000, time.UTC)
	if got := formatFileTimestamp(value, true); got != "2026-08-12 15:42:07 -04:00" {
		t.Fatalf("unexpected timestamp: %q", got)
	}
}

func TestFormatFileTimestampUnknown(t *testing.T) {
	for _, tc := range []struct {
		name      string
		value     time.Time
		available bool
	}{
		{name: "unavailable", value: time.Now(), available: false},
		{name: "zero", value: time.Time{}, available: true},
		{name: "out of range", value: time.Date(10000, 1, 1, 0, 0, 0, 0, time.UTC), available: true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if got := formatFileTimestamp(tc.value, tc.available); got != "unknown" {
				t.Fatalf("got %q want unknown", got)
			}
		})
	}
}
