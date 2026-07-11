#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static uint64_t now_ns(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) {
        return 0;
    }
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static int parse_u64(const char *text, uint64_t *out) {
    char *end = NULL;
    errno = 0;
    unsigned long long value = strtoull(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0') {
        return -1;
    }
    *out = (uint64_t)value;
    return 0;
}

static void json_escape_string(const char *text) {
    putchar('"');
    for (const unsigned char *p = (const unsigned char *)text; *p; ++p) {
        if (*p == '"' || *p == '\\') {
            putchar('\\');
            putchar(*p);
        } else if (*p >= 0x20 && *p <= 0x7e) {
            putchar(*p);
        } else {
            printf("\\u%04x", *p);
        }
    }
    putchar('"');
}

int main(int argc, char **argv) {
    if (argc < 3 || argc > 4) {
        fprintf(stderr, "usage: %s <zonefs-seq-file> <blocks> [chunk-blocks]\n", argv[0]);
        return 2;
    }

    const char *path = argv[1];
    uint64_t blocks = 0;
    uint64_t chunk_blocks = 1024;
    if (parse_u64(argv[2], &blocks) != 0 || blocks == 0) {
        fprintf(stderr, "invalid block count: %s\n", argv[2]);
        return 2;
    }
    if (argc == 4 && (parse_u64(argv[3], &chunk_blocks) != 0 || chunk_blocks == 0)) {
        fprintf(stderr, "invalid chunk block count: %s\n", argv[3]);
        return 2;
    }

    const size_t block_size = 4096;
    size_t chunk_bytes = (size_t)chunk_blocks * block_size;
    void *buffer = NULL;
    if (posix_memalign(&buffer, block_size, chunk_bytes) != 0) {
        fprintf(stderr, "posix_memalign failed\n");
        return 3;
    }
    memset(buffer, 0, chunk_bytes);

    uint64_t started = now_ns();
    int fd = open(path, O_WRONLY | O_APPEND | O_DIRECT);
    if (fd < 0) {
        int saved = errno;
        free(buffer);
        fprintf(stderr, "open failed: %s\n", strerror(saved));
        return 4;
    }

    uint64_t remaining_blocks = blocks;
    uint64_t bytes_written = 0;
    while (remaining_blocks > 0) {
        uint64_t this_blocks = remaining_blocks < chunk_blocks ? remaining_blocks : chunk_blocks;
        size_t this_bytes = (size_t)this_blocks * block_size;
        size_t done = 0;
        while (done < this_bytes) {
            ssize_t ret = write(fd, (char *)buffer + done, this_bytes - done);
            if (ret < 0) {
                int saved = errno;
                close(fd);
                free(buffer);
                fprintf(stderr, "write failed after %llu bytes: %s\n",
                        (unsigned long long)bytes_written, strerror(saved));
                return 5;
            }
            if (ret == 0) {
                close(fd);
                free(buffer);
                fprintf(stderr, "write returned 0 after %llu bytes\n", (unsigned long long)bytes_written);
                return 6;
            }
            done += (size_t)ret;
            bytes_written += (uint64_t)ret;
        }
        remaining_blocks -= this_blocks;
    }

    int close_rc = close(fd);
    uint64_t elapsed = now_ns() - started;
    free(buffer);

    if (close_rc != 0) {
        fprintf(stderr, "close failed: %s\n", strerror(errno));
        return 7;
    }

    printf("{\"path\":");
    json_escape_string(path);
    printf(",\"blocks\":%llu,\"bytes_written\":%llu,\"elapsed_ns\":%llu}\n",
           (unsigned long long)blocks,
           (unsigned long long)bytes_written,
           (unsigned long long)elapsed);
    return 0;
}
