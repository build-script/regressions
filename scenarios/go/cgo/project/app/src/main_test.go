package main

import (
	"strings"
	"testing"
)

func TestMessageIsLoud(t *testing.T) {
	if got := message(); !strings.Contains(got, "FROM C") {
		t.Errorf("message() = %q, want the greeting of C in capitals", got)
	}
}
