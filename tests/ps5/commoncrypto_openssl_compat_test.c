// SPDX-License-Identifier: GPL-3.0-or-later
#include "commoncrypto_openssl_compat.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int hex_eq(const uint8_t* data, size_t size, const char* hex) {
    static const char digits[] = "0123456789abcdef";
    for (size_t i = 0; i < size; ++i) {
        if (digits[data[i] >> 4] != hex[2 * i] ||
            digits[data[i] & 15] != hex[2 * i + 1])
            return 0;
    }
    return hex[2 * size] == '\0';
}

int main(void) {
    {
        CC_SHA256_CTX ctx;
        uint8_t digest[32];
        assert(CC_SHA256_Init(&ctx) == 1);
        assert(CC_SHA256_Update(&ctx, "abc", 3) == 1);
        assert(CC_SHA256_Final(digest, &ctx) == 1);
        assert(hex_eq(
            digest, sizeof digest,
            "ba7816bf8f01cfea414140de5dae2223"
            "b00361a396177a9cb410ff61f20015ad"));
    }

    {
        CCHmacContext first = {0}, copy = {0};
        uint8_t a[32], b[32];
        CCHmacInit(&first, kCCHmacAlgSHA256, "key", 3);
        assert(first.ctx != NULL);
        CCHmacUpdate(&first, "The quick ", 10);
        assert(refrozen_ps5_cchmac_copy(&copy, &first));
        CCHmacUpdate(&first, "brown fox jumps over the lazy dog", 33);
        CCHmacUpdate(&copy, "brown fox jumps over the lazy dog", 33);
        CCHmacFinal(&first, a);
        CCHmacFinal(&copy, b);
        assert(memcmp(a, b, sizeof a) == 0);
        assert(hex_eq(
            a, sizeof a,
            "f7bc83f430538424b13298e6aa6fb143"
            "ef4d59a14946175997479dbc2d1a3cd8"));
        refrozen_ps5_cchmac_cleanup(&first);
        refrozen_ps5_cchmac_cleanup(&copy);
    }

    {
        const uint8_t key[16] = {
            0x2b,0x7e,0x15,0x16,0x28,0xae,0xd2,0xa6,
            0xab,0xf7,0x15,0x88,0x09,0xcf,0x4f,0x3c
        };
        uint8_t iv[16] = {
            0x00,0x01,0x02,0x03,0x04,0x05,0x06,0x07,
            0x08,0x09,0x0a,0x0b,0x0c,0x0d,0x0e,0x0f
        };
        const uint8_t plain[16] = {
            0x6b,0xc1,0xbe,0xe2,0x2e,0x40,0x9f,0x96,
            0xe9,0x3d,0x7e,0x11,0x73,0x93,0x17,0x2a
        };
        const uint8_t expected[16] = {
            0x76,0x49,0xab,0xac,0x81,0x19,0xb2,0x46,
            0xce,0xe9,0x8e,0x9b,0x12,0xe9,0x19,0x7d
        };
        uint8_t encrypted[16], decrypted[16];
        size_t moved = 0;
        assert(CCCrypt(
            kCCEncrypt, kCCAlgorithmAES, 0, key, sizeof key, iv,
            plain, sizeof plain, encrypted, sizeof encrypted, &moved) == kCCSuccess);
        assert(moved == sizeof plain);
        assert(memcmp(encrypted, expected, sizeof expected) == 0);
        assert(CCCrypt(
            kCCDecrypt, kCCAlgorithmAES, 0, key, sizeof key, iv,
            encrypted, sizeof encrypted, decrypted, sizeof decrypted, &moved) == kCCSuccess);
        assert(moved == sizeof plain);
        assert(memcmp(decrypted, plain, sizeof plain) == 0);
    }

    puts("commoncrypto_openssl_compat: PASS");
    return 0;
}
