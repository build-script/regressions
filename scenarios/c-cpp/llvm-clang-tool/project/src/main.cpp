#include <cstdio>

#include "clang/AST/ASTConsumer.h"
#include "clang/AST/RecursiveASTVisitor.h"
#include "clang/Frontend/CompilerInstance.h"
#include "clang/Frontend/FrontendAction.h"
#include "clang/Tooling/Tooling.h"

// counts the functions a piece of C++ defines, with the parser and the AST of Clang
class FunctionCounter : public clang::RecursiveASTVisitor<FunctionCounter> {
public:
    bool VisitFunctionDecl(clang::FunctionDecl *function) {
        if (function->isThisDeclarationADefinition()) {
            std::printf("  %s\n", function->getNameAsString().c_str());
            ++count;
        }
        return true;
    }

    int count = 0;
};

class CountingConsumer : public clang::ASTConsumer {
public:
    void HandleTranslationUnit(clang::ASTContext &context) override {
        FunctionCounter counter;
        counter.TraverseDecl(context.getTranslationUnitDecl());
        std::printf("%d function(s)\n", counter.count);
    }
};

class CountingAction : public clang::ASTFrontendAction {
public:
    std::unique_ptr<clang::ASTConsumer> CreateASTConsumer(clang::CompilerInstance &, llvm::StringRef) override {
        return std::make_unique<CountingConsumer>();
    }
};

int main() {
    const char *code = "int square(int x) { return x * x; }\n"
                       "struct Point { int x, y; int sum() const { return x + y; } };\n"
                       "int declared(int);\n";
    return clang::tooling::runToolOnCode(std::make_unique<CountingAction>(), code, "input.cpp") ? 0 : 1;
}
