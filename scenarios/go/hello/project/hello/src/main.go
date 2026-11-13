package main

import (
	"fmt"

	"github.com/google/uuid"
)

// Greeting is what the program says to a name
func Greeting(name string) string {
	return "Hello, " + name
}

func main() {
	id := uuid.NewSHA1(uuid.NameSpaceURL, []byte("https://example.com"))
	fmt.Println(Greeting("Go"), "with a UUID of version", id.Version())
}
