#include <stdio.h>
#include <sqlite3.h>

int main(void) {
    sqlite3 *db;
    char *error = NULL;
    sqlite3_open(":memory:", &db);
    int status = sqlite3_exec(db, "CREATE VIRTUAL TABLE notes USING fts5(text); INSERT INTO notes VALUES ('vcpkg features');", NULL, NULL, &error);
    printf("fts5: %s\n", status == SQLITE_OK ? "ok" : error);
    sqlite3_close(db);
    return status;
}
