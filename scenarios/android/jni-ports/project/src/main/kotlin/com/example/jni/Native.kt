package com.example.jni

external fun greet(name: String): String

fun loadGreeter() = System.loadLibrary("greeter")
