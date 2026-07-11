// SPDX-License-Identifier: MIT
//
// Minimal OpenSSL 3 + oqsprovider KEM/signature probe.
//
// The OpenSSL 3.0.2 CLI on this host can load oqsprovider but does not expose
// KEM encapsulation through pkeyutl. This helper uses the EVP_PKEY
// encapsulate/decapsulate API directly and emits JSONL measurements that the
// Python trace wrapper converts into QUASAR events.

#define _POSIX_C_SOURCE 200809L

#include <openssl/crypto.h>
#include <openssl/err.h>
#include <openssl/evp.h>
#include <openssl/provider.h>

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define OQS_PROPQ "provider=oqsprovider"

static uint64_t now_ns(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) {
        return 0;
    }
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static void print_errors(const char *label) {
    fprintf(stderr, "%s\n", label);
    ERR_print_errors_fp(stderr);
}

static EVP_PKEY *generate_key(OSSL_LIB_CTX *libctx, const char *alg,
                              uint64_t *elapsed_ns) {
    EVP_PKEY_CTX *ctx = NULL;
    EVP_PKEY *key = NULL;
    uint64_t started = now_ns();

    ctx = EVP_PKEY_CTX_new_from_name(libctx, alg, OQS_PROPQ);
    if (ctx == NULL) {
        print_errors("EVP_PKEY_CTX_new_from_name failed");
        goto err;
    }
    if (EVP_PKEY_keygen_init(ctx) <= 0) {
        print_errors("EVP_PKEY_keygen_init failed");
        goto err;
    }
    if (EVP_PKEY_generate(ctx, &key) <= 0) {
        print_errors("EVP_PKEY_generate failed");
        goto err;
    }

    *elapsed_ns = now_ns() - started;
    EVP_PKEY_CTX_free(ctx);
    return key;

err:
    EVP_PKEY_free(key);
    EVP_PKEY_CTX_free(ctx);
    return NULL;
}

static int run_kem(OSSL_LIB_CTX *libctx, const char *kem_alg,
                   uint64_t *keygen_ns, uint64_t *encap_ns,
                   uint64_t *decap_ns, size_t *ciphertext_len,
                   size_t *secret_len) {
    EVP_PKEY *key = NULL;
    EVP_PKEY_CTX *ctx = NULL;
    unsigned char *ct = NULL;
    unsigned char *secret_enc = NULL;
    unsigned char *secret_dec = NULL;
    size_t ct_len = 0;
    size_t sec_len = 0;
    size_t dec_len = 0;
    uint64_t started = 0;
    int ok = 0;

    key = generate_key(libctx, kem_alg, keygen_ns);
    if (key == NULL) {
        goto err;
    }

    ctx = EVP_PKEY_CTX_new_from_pkey(libctx, key, OQS_PROPQ);
    if (ctx == NULL) {
        print_errors("EVP_PKEY_CTX_new_from_pkey failed for KEM");
        goto err;
    }
    if (EVP_PKEY_encapsulate_init(ctx, NULL) <= 0) {
        print_errors("EVP_PKEY_encapsulate_init failed");
        goto err;
    }
    if (EVP_PKEY_encapsulate(ctx, NULL, &ct_len, NULL, &sec_len) <= 0) {
        print_errors("EVP_PKEY_encapsulate length query failed");
        goto err;
    }

    ct = OPENSSL_malloc(ct_len);
    secret_enc = OPENSSL_malloc(sec_len);
    secret_dec = OPENSSL_malloc(sec_len);
    if (ct == NULL || secret_enc == NULL || secret_dec == NULL) {
        print_errors("OPENSSL_malloc failed");
        goto err;
    }

    started = now_ns();
    if (EVP_PKEY_encapsulate(ctx, ct, &ct_len, secret_enc, &sec_len) <= 0) {
        print_errors("EVP_PKEY_encapsulate failed");
        goto err;
    }
    *encap_ns = now_ns() - started;

    if (EVP_PKEY_decapsulate_init(ctx, NULL) <= 0) {
        print_errors("EVP_PKEY_decapsulate_init failed");
        goto err;
    }
    dec_len = sec_len;
    started = now_ns();
    if (EVP_PKEY_decapsulate(ctx, secret_dec, &dec_len, ct, ct_len) <= 0) {
        print_errors("EVP_PKEY_decapsulate failed");
        goto err;
    }
    *decap_ns = now_ns() - started;

    ok = dec_len == sec_len && memcmp(secret_enc, secret_dec, sec_len) == 0;
    *ciphertext_len = ct_len;
    *secret_len = sec_len;

err:
    OPENSSL_free(ct);
    OPENSSL_free(secret_enc);
    OPENSSL_free(secret_dec);
    EVP_PKEY_CTX_free(ctx);
    EVP_PKEY_free(key);
    return ok;
}

static int run_signature(OSSL_LIB_CTX *libctx, const char *sig_alg,
                         const unsigned char *msg, size_t msg_len,
                         uint64_t *keygen_ns, uint64_t *sign_ns,
                         uint64_t *verify_ns, size_t *signature_len) {
    EVP_PKEY *key = NULL;
    EVP_PKEY_CTX *ctx = NULL;
    unsigned char *sig = NULL;
    size_t sig_len = 0;
    uint64_t started = 0;
    int ok = 0;

    key = generate_key(libctx, sig_alg, keygen_ns);
    if (key == NULL) {
        goto err;
    }

    ctx = EVP_PKEY_CTX_new_from_pkey(libctx, key, OQS_PROPQ);
    if (ctx == NULL) {
        print_errors("EVP_PKEY_CTX_new_from_pkey failed for signature");
        goto err;
    }
    if (EVP_PKEY_sign_init(ctx) <= 0) {
        print_errors("EVP_PKEY_sign_init failed");
        goto err;
    }
    if (EVP_PKEY_sign(ctx, NULL, &sig_len, msg, msg_len) <= 0) {
        print_errors("EVP_PKEY_sign length query failed");
        goto err;
    }
    sig = OPENSSL_malloc(sig_len);
    if (sig == NULL) {
        print_errors("OPENSSL_malloc failed for signature");
        goto err;
    }

    started = now_ns();
    if (EVP_PKEY_sign(ctx, sig, &sig_len, msg, msg_len) <= 0) {
        print_errors("EVP_PKEY_sign failed");
        goto err;
    }
    *sign_ns = now_ns() - started;

    if (EVP_PKEY_verify_init(ctx) <= 0) {
        print_errors("EVP_PKEY_verify_init failed");
        goto err;
    }
    started = now_ns();
    ok = EVP_PKEY_verify(ctx, sig, sig_len, msg, msg_len) == 1;
    *verify_ns = now_ns() - started;
    *signature_len = sig_len;

err:
    OPENSSL_free(sig);
    EVP_PKEY_CTX_free(ctx);
    EVP_PKEY_free(key);
    return ok;
}

int main(int argc, char **argv) {
    int sessions = 0;
    const char *kem_alg = NULL;
    const char *sig_alg = NULL;
    OSSL_LIB_CTX *libctx = NULL;
    OSSL_PROVIDER *default_provider = NULL;
    OSSL_PROVIDER *oqs_provider = NULL;
    int rc = 1;

    if (argc != 4) {
        fprintf(stderr, "usage: %s <sessions> <kem_alg> <sig_alg>\n", argv[0]);
        return 2;
    }
    sessions = atoi(argv[1]);
    kem_alg = argv[2];
    sig_alg = argv[3];
    if (sessions <= 0) {
        fprintf(stderr, "sessions must be positive\n");
        return 2;
    }

    libctx = OSSL_LIB_CTX_new();
    if (libctx == NULL) {
        print_errors("OSSL_LIB_CTX_new failed");
        goto out;
    }
    default_provider = OSSL_PROVIDER_load(libctx, "default");
    oqs_provider = OSSL_PROVIDER_load(libctx, "oqsprovider");
    if (default_provider == NULL || oqs_provider == NULL) {
        print_errors("OSSL_PROVIDER_load failed");
        goto out;
    }

    for (int i = 0; i < sessions; i++) {
        char msg[128];
        uint64_t kem_keygen_ns = 0;
        uint64_t kem_encap_ns = 0;
        uint64_t kem_decap_ns = 0;
        uint64_t sig_keygen_ns = 0;
        uint64_t sig_sign_ns = 0;
        uint64_t sig_verify_ns = 0;
        size_t ciphertext_len = 0;
        size_t shared_secret_len = 0;
        size_t signature_len = 0;
        int kem_ok = 0;
        int sig_ok = 0;

        snprintf(msg, sizeof(msg), "quasar-openssl-oqs-session-%d", i);
        kem_ok = run_kem(libctx, kem_alg, &kem_keygen_ns, &kem_encap_ns,
                         &kem_decap_ns, &ciphertext_len, &shared_secret_len);
        sig_ok = run_signature(libctx, sig_alg, (const unsigned char *)msg,
                               strlen(msg), &sig_keygen_ns, &sig_sign_ns,
                               &sig_verify_ns, &signature_len);
        if (!kem_ok || !sig_ok) {
            fprintf(stderr, "session %d failed: kem_ok=%d sig_ok=%d\n", i,
                    kem_ok, sig_ok);
            goto out;
        }

        printf("{\"session\":%d,\"kem\":\"%s\",\"sig\":\"%s\","
               "\"kem_ok\":true,\"sig_ok\":true,"
               "\"ciphertext_bytes\":%zu,\"shared_secret_bytes\":%zu,"
               "\"signature_bytes\":%zu,"
               "\"kem_keygen_ns\":%llu,\"kem_encap_ns\":%llu,"
               "\"kem_decap_ns\":%llu,\"sig_keygen_ns\":%llu,"
               "\"sig_sign_ns\":%llu,\"sig_verify_ns\":%llu}\n",
               i, kem_alg, sig_alg, ciphertext_len, shared_secret_len,
               signature_len, (unsigned long long)kem_keygen_ns,
               (unsigned long long)kem_encap_ns,
               (unsigned long long)kem_decap_ns,
               (unsigned long long)sig_keygen_ns,
               (unsigned long long)sig_sign_ns,
               (unsigned long long)sig_verify_ns);
    }

    rc = 0;

out:
    OSSL_PROVIDER_unload(oqs_provider);
    OSSL_PROVIDER_unload(default_provider);
    OSSL_LIB_CTX_free(libctx);
    return rc;
}
