// SPDX-License-Identifier: GPL-3.0-or-later
// Host x86-64 contract test for the PS5 fiber switch sequence.
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

__attribute__((naked)) static void swap_ctx(uint64_t *save_sp, uint64_t new_sp) {
    __asm__ volatile(
        "pushq %rbx\n"
        "pushq %rbp\n"
        "pushq %r12\n"
        "pushq %r13\n"
        "pushq %r14\n"
        "pushq %r15\n"
        "movq %rsp, (%rdi)\n"
        "movq %rsi, %rsp\n"
        "popq %r15\n"
        "popq %r14\n"
        "popq %r13\n"
        "popq %r12\n"
        "popq %rbp\n"
        "popq %rbx\n"
        "retq\n");
}

static unsigned char fiber_stack[64 * 1024] __attribute__((aligned(16)));
static uint64_t main_sp;
static uint64_t fiber_sp;
static int phase;

__attribute__((noinline, noreturn)) static void fiber_entry(void) {
    phase = 1;
    swap_ctx(&fiber_sp, main_sp);
    phase = 2;
    swap_ctx(&fiber_sp, main_sp);
    __builtin_trap();
}

int main(void) {
    const uint64_t top =
        (uint64_t)(uintptr_t)(fiber_stack + sizeof fiber_stack);
    const uint64_t sp = (top - 56u) & ~UINT64_C(0xF);
    memset((void *)(uintptr_t)sp, 0, 56);
    *(uint64_t *)(uintptr_t)(sp + 48) =
        (uint64_t)(uintptr_t)&fiber_entry;
    fiber_sp = sp;

    assert((fiber_sp & 0xF) == 0);
    swap_ctx(&main_sp, fiber_sp);
    assert(phase == 1);
    assert(main_sp != 0);
    assert(fiber_sp != 0);

    swap_ctx(&main_sp, fiber_sp);
    assert(phase == 2);

    puts("x86_64_fiber_swap: PASS");
    return 0;
}
