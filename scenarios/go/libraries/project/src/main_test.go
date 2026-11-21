package main

import "testing"

func TestGreeting(t *testing.T) {
	if greeting() != "Hello with cobra and a UUID of version 5" {
		t.Errorf("greeting() = %q", greeting())
	}
}
