package main

// #include "greet.h"
// #include "shout.h"
import "C"

import "fmt"

func message() string {
	return fmt.Sprintf("%s (%d times)", C.GoString(C.shout(C.greet())), C.GREET_TIMES)
}

func main() {
	fmt.Println(message())
}
