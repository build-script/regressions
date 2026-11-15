#include <jni.h>

#include <string>

#include "shout/shout.hpp"

// greet(name) of com.example.Native, in C++ with a static library linked in
extern "C" JNIEXPORT jstring JNICALL Java_com_example_jni_NativeKt_greet(JNIEnv *env, jclass, jstring name) {
    const char *chars = env->GetStringUTFChars(name, nullptr);
    std::string greeting = "Hello, " + shout(chars) + ", from C++";
    env->ReleaseStringUTFChars(name, chars);
    return env->NewStringUTF(greeting.c_str());
}
