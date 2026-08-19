#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* CPU-only process/OCI launch fixture. It performs no file or network I/O. */

static const char expected[] = "{\"value\":\"catalog-switch-cpu-fixture\"}\n";
static const char response[] =
    "{\"model_id\":\"cpu-fixture-b\",\"model_version\":\"v1\","
    "\"result\":\"semantically-valid\"}\n";

int main(void) {
    char input[128];
    size_t used = 0;

    if (fputs("READY\n", stdout) == EOF || fflush(stdout) != 0) {
        return 70;
    }
    while (used < sizeof(input) - 1) {
        int value = fgetc(stdin);
        if (value == EOF) {
            if (ferror(stdin)) {
                return 74;
            }
            break;
        }
        input[used++] = (char)value;
        if (value == '\n') {
            break;
        }
    }
    input[used] = '\0';
    if (used == sizeof(input) - 1 && input[used - 1] != '\n') {
        return 65;
    }
    if (strcmp(input, expected) != 0) {
        return 66;
    }
    if (fputs(response, stdout) == EOF || fflush(stdout) != 0) {
        return 74;
    }
    return 0;
}
