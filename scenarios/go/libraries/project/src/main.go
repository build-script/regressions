package main

import (
	"fmt"

	"github.com/google/uuid"
	"github.com/spf13/cobra"
)

// greeting is what the program says, with the version of a UUID
func greeting() string {
	id := uuid.NewSHA1(uuid.NameSpaceURL, []byte("https://example.com"))
	return fmt.Sprintf("Hello with cobra and a UUID of version %d", id.Version())
}

func main() {
	command := &cobra.Command{Use: "hello", Run: func(*cobra.Command, []string) { fmt.Println(greeting()) }}
	command.Execute()
}
