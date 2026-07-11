#define _POSIX_C_SOURCE 200809L

// C-level policy decision microbenchmark for QUASAR vs DOGI-style placement.
//
// This benchmark intentionally measures only placement-decision CPU cost. It
// does not simulate SSD I/O or GC. DOGI-style cost is modeled as storage-visible
// feature extraction plus a small MLP inference; QUASAR cost is modeled as
// intent/epoch parsing plus a zone-family table lookup.

#include <ctype.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <time.h>

enum op_code {
    OP_OTHER = 0,
    OP_WRITE = 1,
    OP_PREFILL = 2,
    OP_EXPIRE = 3,
};

enum intent_code {
    INTENT_PAYLOAD = 0,
    INTENT_EPHEMERAL_SECRET = 1,
    INTENT_KEM_ARTIFACT = 2,
    INTENT_SIGNATURE_LOG = 3,
    INTENT_CERT_METADATA = 4,
    INTENT_UNKNOWN = 5,
};

enum security_code {
    SECURITY_PAYLOAD = 0,
    SECURITY_SECRET = 1,
    SECURITY_PUBLIC_METADATA = 2,
    SECURITY_UNKNOWN = 3,
};

struct event {
    uint64_t ts;
    uint64_t object_id;
    uint64_t lba;
    uint64_t epoch_id;
    uint64_t size_blocks;
    uint32_t op;
    uint32_t intent;
    uint32_t security;
};

struct trace {
    struct event *events;
    size_t count;
    size_t writes;
    size_t expires;
};

struct dogi_state {
    uint64_t *last_ts;
    uint64_t *last_lba;
    uint32_t *freq;
    size_t buckets;
    uint64_t prev_lba;
};

struct family_entry {
    uint64_t key;
    uint32_t used;
    uint32_t zone_id;
};

struct quasar_state {
    struct family_entry *entries;
    size_t capacity;
    uint32_t next_zone;
};

struct sample {
    const char *policy;
    uint64_t elapsed_ns;
    double ns_per_event;
    double ns_per_write;
};

static volatile uint64_t sink_u64 = 0;
static volatile double sink_double = 0.0;

static uint64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static uint64_t hash64(uint64_t x) {
    x ^= x >> 33;
    x *= 0xff51afd7ed558ccdULL;
    x ^= x >> 33;
    x *= 0xc4ceb9fe1a85ec53ULL;
    x ^= x >> 33;
    return x;
}

static const char *find_value(const char *line, const char *key) {
    const char *p = strstr(line, key);
    if (!p) {
        return NULL;
    }
    p = strchr(p, ':');
    if (!p) {
        return NULL;
    }
    ++p;
    while (*p && isspace((unsigned char)*p)) {
        ++p;
    }
    return p;
}

static uint64_t parse_u64(const char *line, const char *key, uint64_t default_value) {
    const char *p = find_value(line, key);
    if (!p || !isdigit((unsigned char)*p)) {
        return default_value;
    }
    return strtoull(p, NULL, 10);
}

static int parse_string(const char *line, const char *key, char *out, size_t out_len) {
    const char *p = find_value(line, key);
    size_t i = 0;
    if (!p || *p != '"') {
        return 0;
    }
    ++p;
    while (*p && *p != '"' && i + 1 < out_len) {
        out[i++] = *p++;
    }
    out[i] = '\0';
    return i > 0;
}

static uint32_t parse_op(const char *line) {
    char value[32];
    if (!parse_string(line, "\"op\"", value, sizeof(value))) {
        return OP_OTHER;
    }
    if (strcmp(value, "write") == 0) {
        return OP_WRITE;
    }
    if (strcmp(value, "prefill") == 0) {
        return OP_PREFILL;
    }
    if (strcmp(value, "expire") == 0) {
        return OP_EXPIRE;
    }
    return OP_OTHER;
}

static uint32_t parse_intent(const char *line) {
    char value[64];
    if (!parse_string(line, "\"intent\"", value, sizeof(value))) {
        return INTENT_UNKNOWN;
    }
    if (strcmp(value, "PAYLOAD") == 0) {
        return INTENT_PAYLOAD;
    }
    if (strcmp(value, "EPHEMERAL_SECRET") == 0) {
        return INTENT_EPHEMERAL_SECRET;
    }
    if (strcmp(value, "KEM_ARTIFACT") == 0) {
        return INTENT_KEM_ARTIFACT;
    }
    if (strcmp(value, "SIGNATURE_LOG") == 0) {
        return INTENT_SIGNATURE_LOG;
    }
    if (strcmp(value, "CERT_METADATA") == 0) {
        return INTENT_CERT_METADATA;
    }
    return INTENT_UNKNOWN;
}

static uint32_t parse_security(const char *line) {
    char value[64];
    if (!parse_string(line, "\"security_class\"", value, sizeof(value))) {
        return SECURITY_UNKNOWN;
    }
    if (strcmp(value, "PAYLOAD") == 0) {
        return SECURITY_PAYLOAD;
    }
    if (strcmp(value, "SECRET") == 0) {
        return SECURITY_SECRET;
    }
    if (strcmp(value, "PUBLIC_METADATA") == 0) {
        return SECURITY_PUBLIC_METADATA;
    }
    return SECURITY_UNKNOWN;
}

static int load_trace(const char *path, struct trace *out) {
    FILE *fp = fopen(path, "r");
    char *line = NULL;
    size_t line_cap = 0;
    ssize_t line_len;
    size_t capacity = 8192;

    if (!fp) {
        perror(path);
        return 0;
    }

    out->events = (struct event *)calloc(capacity, sizeof(struct event));
    if (!out->events) {
        fclose(fp);
        return 0;
    }
    out->count = 0;
    out->writes = 0;
    out->expires = 0;

    while ((line_len = getline(&line, &line_cap, fp)) >= 0) {
        (void)line_len;
        if (out->count == capacity) {
            capacity *= 2;
            struct event *next = (struct event *)realloc(out->events, capacity * sizeof(struct event));
            if (!next) {
                free(line);
                fclose(fp);
                return 0;
            }
            out->events = next;
        }

        struct event ev;
        memset(&ev, 0, sizeof(ev));
        ev.op = parse_op(line);
        ev.intent = parse_intent(line);
        ev.security = parse_security(line);
        ev.ts = parse_u64(line, "\"ts\"", 0);
        ev.object_id = parse_u64(line, "\"object_id\"", 0);
        ev.lba = parse_u64(line, "\"lba\"", 0);
        ev.epoch_id = parse_u64(line, "\"epoch_id\"", 0);
        ev.size_blocks = parse_u64(line, "\"size_blocks\"", 1);
        if (ev.op == OP_WRITE || ev.op == OP_PREFILL) {
            out->writes++;
        } else if (ev.op == OP_EXPIRE) {
            out->expires++;
        }
        out->events[out->count++] = ev;
    }

    free(line);
    fclose(fp);
    return 1;
}

static void free_trace(struct trace *trace) {
    free(trace->events);
    trace->events = NULL;
    trace->count = 0;
}

static int dogi_init(struct dogi_state *state, size_t buckets) {
    state->buckets = buckets;
    state->prev_lba = 0;
    state->last_ts = (uint64_t *)calloc(buckets, sizeof(uint64_t));
    state->last_lba = (uint64_t *)calloc(buckets, sizeof(uint64_t));
    state->freq = (uint32_t *)calloc(buckets, sizeof(uint32_t));
    return state->last_ts && state->last_lba && state->freq;
}

static void dogi_free(struct dogi_state *state) {
    free(state->last_ts);
    free(state->last_lba);
    free(state->freq);
    memset(state, 0, sizeof(*state));
}

static double dogi_mlp(float features[6]) {
    double hidden[16];
    for (int h = 0; h < 16; ++h) {
        double acc = 0.03125 * (double)(h + 1);
        for (int f = 0; f < 6; ++f) {
            double weight = (double)(((h + 3) * (f + 5)) % 17 - 8) / 32.0;
            acc += (double)features[f] * weight;
        }
        hidden[h] = acc > 0.0 ? acc : 0.0;
    }
    double out = 0.0;
    for (int h = 0; h < 16; ++h) {
        double weight = (double)((h * 7) % 13 - 6) / 16.0;
        out += hidden[h] * weight;
    }
    return out;
}

static void dogi_write(struct dogi_state *state, const struct event *ev) {
    size_t bucket = (size_t)hash64(ev->lba >> 12) & (state->buckets - 1);
    uint64_t last_ts = state->last_ts[bucket];
    uint64_t interval = last_ts ? ev->ts - last_ts : 0;
    uint64_t prev_delta = ev->lba > state->prev_lba ? ev->lba - state->prev_lba : state->prev_lba - ev->lba;
    uint32_t freq = ++state->freq[bucket];

    float features[6];
    features[0] = (float)(ev->lba & 0xffffu) / 65536.0f;
    features[1] = (float)(prev_delta & 0xffffu) / 65536.0f;
    features[2] = (float)(interval & 0xffffu) / 65536.0f;
    features[3] = freq > 1 ? 1.0f : 0.0f;
    features[4] = freq > 8 ? 1.0f : 0.0f;
    features[5] = state->last_lba[bucket] != 0 ? 1.0f : 0.0f;

    state->last_ts[bucket] = ev->ts;
    state->last_lba[bucket] = ev->lba;
    state->prev_lba = ev->lba;
    sink_double += dogi_mlp(features);
}

static int quasar_init(struct quasar_state *state, size_t capacity) {
    state->capacity = capacity;
    state->next_zone = 1;
    state->entries = (struct family_entry *)calloc(capacity, sizeof(struct family_entry));
    return state->entries != NULL;
}

static void quasar_free(struct quasar_state *state) {
    free(state->entries);
    memset(state, 0, sizeof(*state));
}

static uint64_t quasar_family_key(const struct event *ev) {
    uint64_t epoch = ev->epoch_id;
    uint64_t intent = ev->intent;
    uint64_t security = ev->security;

    if (ev->intent == INTENT_PAYLOAD || ev->intent == INTENT_UNKNOWN) {
        return hash64(0xfeed0001ULL ^ (ev->lba >> 12));
    }
    if (ev->intent == INTENT_CERT_METADATA) {
        epoch = epoch / 12;
    } else if (ev->intent == INTENT_SIGNATURE_LOG) {
        epoch = 0;
    }
    return hash64((intent << 56) ^ (security << 48) ^ epoch);
}

static uint32_t quasar_lookup(struct quasar_state *state, uint64_t key) {
    size_t idx = (size_t)key & (state->capacity - 1);
    for (size_t probe = 0; probe < state->capacity; ++probe) {
        struct family_entry *entry = &state->entries[idx];
        if (!entry->used) {
            entry->used = 1;
            entry->key = key;
            entry->zone_id = state->next_zone++;
            return entry->zone_id;
        }
        if (entry->key == key) {
            return entry->zone_id;
        }
        idx = (idx + 1) & (state->capacity - 1);
    }
    return 0;
}

static void quasar_write(struct quasar_state *state, const struct event *ev) {
    uint64_t key = quasar_family_key(ev);
    uint32_t zone = quasar_lookup(state, key);
    sink_u64 ^= ((uint64_t)zone << 32) ^ key;
}

static uint64_t run_dogi(const struct trace *trace) {
    struct dogi_state state;
    uint64_t start;
    if (!dogi_init(&state, 1u << 20)) {
        fprintf(stderr, "dogi_init failed\n");
        exit(2);
    }
    start = now_ns();
    for (size_t i = 0; i < trace->count; ++i) {
        const struct event *ev = &trace->events[i];
        if (ev->op == OP_WRITE || ev->op == OP_PREFILL) {
            dogi_write(&state, ev);
        } else if (ev->op == OP_EXPIRE) {
            sink_u64 ^= ev->object_id;
        }
    }
    uint64_t elapsed = now_ns() - start;
    dogi_free(&state);
    return elapsed;
}

static uint64_t run_quasar(const struct trace *trace) {
    struct quasar_state state;
    uint64_t start;
    if (!quasar_init(&state, 1u << 20)) {
        fprintf(stderr, "quasar_init failed\n");
        exit(2);
    }
    start = now_ns();
    for (size_t i = 0; i < trace->count; ++i) {
        const struct event *ev = &trace->events[i];
        if (ev->op == OP_WRITE || ev->op == OP_PREFILL) {
            quasar_write(&state, ev);
        } else if (ev->op == OP_EXPIRE) {
            sink_u64 ^= quasar_family_key(ev);
        }
    }
    uint64_t elapsed = now_ns() - start;
    quasar_free(&state);
    return elapsed;
}

static uint64_t run_hybrid(const struct trace *trace) {
    struct dogi_state dogi;
    struct quasar_state quasar;
    uint64_t start;
    if (!dogi_init(&dogi, 1u << 20) || !quasar_init(&quasar, 1u << 20)) {
        fprintf(stderr, "hybrid init failed\n");
        exit(2);
    }
    start = now_ns();
    for (size_t i = 0; i < trace->count; ++i) {
        const struct event *ev = &trace->events[i];
        if (ev->op == OP_WRITE || ev->op == OP_PREFILL) {
            if (ev->intent == INTENT_PAYLOAD || ev->intent == INTENT_UNKNOWN) {
                dogi_write(&dogi, ev);
            } else {
                quasar_write(&quasar, ev);
            }
        } else if (ev->op == OP_EXPIRE) {
            sink_u64 ^= ev->object_id;
        }
    }
    uint64_t elapsed = now_ns() - start;
    dogi_free(&dogi);
    quasar_free(&quasar);
    return elapsed;
}

static int cmp_u64(const void *a, const void *b) {
    uint64_t av = *(const uint64_t *)a;
    uint64_t bv = *(const uint64_t *)b;
    return (av > bv) - (av < bv);
}

static struct sample benchmark_policy(const char *policy, const struct trace *trace, int repeats) {
    uint64_t *values = (uint64_t *)calloc((size_t)repeats, sizeof(uint64_t));
    if (!values) {
        fprintf(stderr, "calloc failed\n");
        exit(2);
    }
    for (int i = 0; i < repeats; ++i) {
        if (strcmp(policy, "dogi-mlp") == 0) {
            values[i] = run_dogi(trace);
        } else if (strcmp(policy, "quasar-hint") == 0) {
            values[i] = run_quasar(trace);
        } else if (strcmp(policy, "quasar-dogi-hybrid") == 0) {
            values[i] = run_hybrid(trace);
        } else {
            fprintf(stderr, "unknown policy: %s\n", policy);
            exit(2);
        }
    }
    qsort(values, (size_t)repeats, sizeof(uint64_t), cmp_u64);
    uint64_t median = values[(size_t)repeats / 2];
    free(values);

    struct sample sample;
    sample.policy = policy;
    sample.elapsed_ns = median;
    sample.ns_per_event = trace->count ? (double)median / (double)trace->count : 0.0;
    sample.ns_per_write = trace->writes ? (double)median / (double)trace->writes : 0.0;
    return sample;
}

static void usage(const char *argv0) {
    fprintf(stderr, "usage: %s --trace TRACE.jsonl [--repeats N]\n", argv0);
}

int main(int argc, char **argv) {
    const char *trace_path = NULL;
    int repeats = 9;
    struct trace trace;
    memset(&trace, 0, sizeof(trace));

    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--trace") == 0 && i + 1 < argc) {
            trace_path = argv[++i];
        } else if (strcmp(argv[i], "--repeats") == 0 && i + 1 < argc) {
            repeats = atoi(argv[++i]);
            if (repeats < 1) {
                repeats = 1;
            }
        } else {
            usage(argv[0]);
            return 2;
        }
    }

    if (!trace_path) {
        usage(argv[0]);
        return 2;
    }
    if (!load_trace(trace_path, &trace)) {
        return 1;
    }

    const char *policies[] = {"dogi-mlp", "quasar-hint", "quasar-dogi-hybrid"};
    struct sample samples[3];
    for (size_t i = 0; i < 3; ++i) {
        samples[i] = benchmark_policy(policies[i], &trace, repeats);
    }

    printf("{\n");
    printf("  \"trace\": \"%s\",\n", trace_path);
    printf("  \"events\": %zu,\n", trace.count);
    printf("  \"writes\": %zu,\n", trace.writes);
    printf("  \"expires\": %zu,\n", trace.expires);
    printf("  \"repeats\": %d,\n", repeats);
    printf("  \"sink_u64\": %llu,\n", (unsigned long long)sink_u64);
    printf("  \"sink_double\": %.6f,\n", sink_double);
    printf("  \"rows\": [\n");
    for (size_t i = 0; i < 3; ++i) {
        printf("    {\"policy\": \"%s\", \"elapsed_ns_median\": %llu, \"ns_per_event_median\": %.3f, \"ns_per_write_median\": %.3f}%s\n",
               samples[i].policy,
               (unsigned long long)samples[i].elapsed_ns,
               samples[i].ns_per_event,
               samples[i].ns_per_write,
               i + 1 == 3 ? "" : ",");
    }
    printf("  ]\n");
    printf("}\n");

    free_trace(&trace);
    return 0;
}
