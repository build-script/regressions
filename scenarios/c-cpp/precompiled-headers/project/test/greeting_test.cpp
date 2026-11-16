std::string greeting();

// the tests take the precompiled headers too, translated with their own flags
int main() {
    return greeting() == greeting_of({"hello", "from", "the", "precompiled", "headers"}) ? 0 : 1;
}
