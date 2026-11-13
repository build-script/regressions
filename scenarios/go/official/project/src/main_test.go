package main

import "testing"

func TestGreeting(t *testing.T) {
	if greeting() == "" {
		t.Error("no greeting")
	}
}
