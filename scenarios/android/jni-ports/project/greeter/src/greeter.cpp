#include <jni.h>

#include <string>

#include <fmt/format.h>

// greet(name) of com.example.Native, in C++ with fmt of vcpkg, built by the NDK for the ABI
extern "C" JNIEXPORT jstring JNICALL Java_com_example_jni_NativeKt_greet(JNIEnv *env, jclass, jstring name) {
    const char *chars = env->GetStringUTFChars(name, nullptr);
    std::string greeting = fmt::format("Hello, {}, from C++ and fmt {}", chars, FMT_VERSION / 10000);
    env->ReleaseStringUTFChars(name, chars);
    return env->NewStringUTF(greeting.c_str());
}
