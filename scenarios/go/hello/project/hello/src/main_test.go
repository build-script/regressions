package main

import "testing"

func TestGreeting(t *testing.T) {
	if got := Greeting("Go"); got != "Hello, Go" {
		t.Errorf("Greeting(\"Go\") = %q", got)
	}
}
