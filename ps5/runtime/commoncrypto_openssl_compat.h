// SPDX-License-Identifier: GPL-3.0-or-later
// Minimal CommonCrypto compatibility surface for the pinned Win64 bcrypt HLE.
// Backed by OpenSSL/libcrypto from Encore's pinned PS5 PacBrew dependencies.
#pragma once

#include <limits.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include <openssl/evp.h>
#include <openssl/hmac.h>
#include <openssl/md5.h>
#include <openssl/sha.h>

typedef unsigned int CC_LONG;
typedef MD5_CTX CC_MD5_CTX;
typedef SHA_CTX CC_SHA1_CTX;
typedef SHA256_CTX CC_SHA256_CTX;
typedef SHA512_CTX CC_SHA512_CTX;

#define CC_MD5_Init MD5_Init
#define CC_MD5_Update MD5_Update
#define CC_MD5_Final MD5_Final
#define CC_SHA1_Init SHA1_Init
#define CC_SHA1_Update SHA1_Update
#define CC_SHA1_Final SHA1_Final
#define CC_SHA256_Init SHA256_Init
#define CC_SHA256_Update SHA256_Update
#define CC_SHA256_Final SHA256_Final
#define CC_SHA384_Init SHA384_Init
#define CC_SHA384_Update SHA384_Update
#define CC_SHA384_Final SHA384_Final
#define CC_SHA512_Init SHA512_Init
#define CC_SHA512_Update SHA512_Update
#define CC_SHA512_Final SHA512_Final

typedef enum {
    kCCHmacAlgSHA1 = 0,
    kCCHmacAlgMD5,
    kCCHmacAlgSHA256,
    kCCHmacAlgSHA384,
    kCCHmacAlgSHA512,
} CCHmacAlgorithm;

typedef struct {
    HMAC_CTX* ctx;
    CCHmacAlgorithm alg;
} CCHmacContext;

static inline const EVP_MD* refrozen_ps5_hmac_md(CCHmacAlgorithm alg) {
    switch (alg) {
        case kCCHmacAlgMD5: return EVP_md5();
        case kCCHmacAlgSHA1: return EVP_sha1();
        case kCCHmacAlgSHA256: return EVP_sha256();
        case kCCHmacAlgSHA384: return EVP_sha384();
        case kCCHmacAlgSHA512: return EVP_sha512();
    }
    return NULL;
}

static inline void CCHmacInit(
    CCHmacContext* context, CCHmacAlgorithm alg, const void* key, size_t key_len) {
    const EVP_MD* md = refrozen_ps5_hmac_md(alg);
    if (!context || !md || key_len > INT_MAX) return;
    if (context->ctx) HMAC_CTX_free(context->ctx);
    context->ctx = HMAC_CTX_new();
    context->alg = alg;
    if (!context->ctx ||
        HMAC_Init_ex(context->ctx, key, (int)key_len, md, NULL) != 1) {
        if (context->ctx) HMAC_CTX_free(context->ctx);
        context->ctx = NULL;
    }
}

static inline void CCHmacUpdate(
    CCHmacContext* context, const void* data, size_t data_len) {
    if (context && context->ctx && (!data_len || data))
        (void)HMAC_Update(context->ctx, (const unsigned char*)data, data_len);
}

static inline void CCHmacFinal(CCHmacContext* context, void* mac_out) {
    unsigned int length = 0;
    if (context && context->ctx && mac_out)
        (void)HMAC_Final(context->ctx, (unsigned char*)mac_out, &length);
}

static inline int refrozen_ps5_cchmac_copy(
    CCHmacContext* dst, const CCHmacContext* src) {
    if (!dst || !src || !src->ctx) return 0;
    memset(dst, 0, sizeof(*dst));
    dst->ctx = HMAC_CTX_new();
    dst->alg = src->alg;
    if (!dst->ctx || HMAC_CTX_copy(dst->ctx, src->ctx) != 1) {
        if (dst->ctx) HMAC_CTX_free(dst->ctx);
        dst->ctx = NULL;
        return 0;
    }
    return 1;
}

static inline void refrozen_ps5_cchmac_cleanup(CCHmacContext* context) {
    if (!context) return;
    if (context->ctx) HMAC_CTX_free(context->ctx);
    context->ctx = NULL;
}

typedef int CCOperation;
enum { kCCEncrypt = 0, kCCDecrypt = 1 };
enum { kCCAlgorithmAES = 0 };
enum { kCCOptionPKCS7Padding = 1 << 0, kCCOptionECBMode = 1 << 1 };
typedef int CCCryptorStatus;
enum {
    kCCSuccess = 0,
    kCCParamError = -4300,
    kCCBufferTooSmall = -4301,
    kCCUnspecifiedError = -4302,
};

static inline const EVP_CIPHER* refrozen_ps5_aes_cipher(
    size_t key_len, int ecb) {
    switch (key_len) {
        case 16: return ecb ? EVP_aes_128_ecb() : EVP_aes_128_cbc();
        case 24: return ecb ? EVP_aes_192_ecb() : EVP_aes_192_cbc();
        case 32: return ecb ? EVP_aes_256_ecb() : EVP_aes_256_cbc();
        default: return NULL;
    }
}

static inline CCCryptorStatus CCCrypt(
    CCOperation operation,
    int algorithm,
    int options,
    const void* key,
    size_t key_len,
    const void* iv,
    const void* data_in,
    size_t data_in_len,
    void* data_out,
    size_t data_out_available,
    size_t* data_out_moved) {
    if (data_out_moved) *data_out_moved = 0;
    if (algorithm != kCCAlgorithmAES || !key || !data_out ||
        (data_in_len && !data_in) || data_in_len > INT_MAX ||
        data_out_available > INT_MAX)
        return kCCParamError;

    const int encrypt = operation == kCCEncrypt;
    if (!encrypt && operation != kCCDecrypt) return kCCParamError;
    const int ecb = (options & kCCOptionECBMode) != 0;
    const int padding = (options & kCCOptionPKCS7Padding) != 0;
    const EVP_CIPHER* cipher = refrozen_ps5_aes_cipher(key_len, ecb);
    if (!cipher || (!ecb && !iv)) return kCCParamError;

    const size_t required =
        encrypt && padding ? (data_in_len / 16 + 1) * 16 : data_in_len;
    if (data_out_available < required)
        return kCCBufferTooSmall;
    if (data_out_available < data_in_len && !padding)
        return kCCBufferTooSmall;

    EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
    if (!ctx) return kCCUnspecifiedError;
    CCCryptorStatus result = kCCUnspecifiedError;
    int first = 0, final = 0;
    if (EVP_CipherInit_ex(ctx, cipher, NULL, NULL, NULL, encrypt) != 1) goto done;
    if (EVP_CIPHER_CTX_set_padding(ctx, padding) != 1) goto done;
    if (EVP_CipherInit_ex(
            ctx, NULL, NULL, (const unsigned char*)key,
            ecb ? NULL : (const unsigned char*)iv, encrypt) != 1)
        goto done;
    if (EVP_CipherUpdate(
            ctx, (unsigned char*)data_out, &first,
            (const unsigned char*)data_in, (int)data_in_len) != 1)
        goto done;
    if ((size_t)first > data_out_available) {
        result = kCCBufferTooSmall;
        goto done;
    }
    if (EVP_CipherFinal_ex(
            ctx, (unsigned char*)data_out + first, &final) != 1)
        goto done;
    if ((size_t)first + (size_t)final > data_out_available) {
        result = kCCBufferTooSmall;
        goto done;
    }
    if (data_out_moved) *data_out_moved = (size_t)first + (size_t)final;
    result = kCCSuccess;

done:
    EVP_CIPHER_CTX_free(ctx);
    return result;
}
