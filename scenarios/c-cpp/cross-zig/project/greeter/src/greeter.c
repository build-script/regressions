#include <jni.h>

JNIEXPORT jint JNICALL Java_Greeter_answer(JNIEnv* environment, jclass type) {
    return 42;
}
