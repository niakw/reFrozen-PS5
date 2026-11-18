#!/usr/bin/env python3
"""Apply fail-closed PS5 bootstrap edits to pinned NightSight runtime/boot.c."""
from __future__ import annotations

import argparse
from pathlib import Path


class PatchError(RuntimeError):
    pass


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        first = old.splitlines()[0] if old.splitlines() else "<empty>"
        raise PatchError(
            f"{path.name}: fragment {first!r} expected once, found {count}"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_between_once(
    path: Path, start: str, end: str, replacement: str
) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(start) != 1 or text.count(end) != 1:
        raise PatchError(
            f"{path.name}: expected unique markers {start!r} / {end!r}"
        )
    begin = text.index(start)
    finish = text.index(end, begin)
    if finish <= begin:
        raise PatchError(f"{path.name}: invalid marker order")
    path.write_text(text[:begin] + replacement + text[finish:], encoding="utf-8")


def patch_boot(runtime: Path) -> None:
    boot = runtime.resolve() / "boot.c"
    if not boot.is_file():
        raise PatchError("pinned runtime is missing boot.c")

    replace_once(
        boot,
        """#include <crt_externs.h>
#include <mach-o/dyld.h>
#include <spawn.h>
""",
        """#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
""",
    )
    replace_once(
        boot,
        """#include "rt.h"
#include "cocoa.h"
#include "game.h"
#include <glob.h>
""",
        """#include "rt.h"
#include "game.h"
""",
    )

    replace_between_once(
        boot,
        "static const char *home_dir(void)",
        "// How this process was started",
        r"""static const char *home_dir(void) {
    const char *home = getenv("HOME");
    return home && *home ? home : "/data";
}
static int is_game_dir(const char *d) {
    char p[PATH_MAX];
    if (!d || !*d) return 0;
    snprintf(p, sizeof p, "%s/%s", d, rt_game.exe);
    return access(p, R_OK) == 0;
}
static char *find_game_dir(void) {
    // A registered PS5 title cannot rely on a shell environment. Let the
    // frontend override the location, keep the development env override, then
    // try the private packaged-data convention used by reFrozen.
    extern const char *rt_ps5_game_dir(void) __attribute__((weak));
    if (rt_ps5_game_dir) {
        const char *frontend = rt_ps5_game_dir();
        if (frontend && is_game_dir(frontend)) return strdup(frontend);
    }
    const char *env = rt_game_env("GAME_DIR");
    if (env && is_game_dir(env)) return strdup(env);
    static const char *const candidates[] = {
        "/app0/game",
        "/data/refrozen/game",
        NULL
    };
    for (int i = 0; candidates[i]; i++)
        if (is_game_dir(candidates[i])) return strdup(candidates[i]);
    rt_log("[boot] PS5 game directory not found; provide frontend path, %s_GAME_DIR, /app0/game or /data/refrozen/game\n",
           rt_game.env_prefix);
    return NULL;
}

""",
    )

    replace_between_once(
        boot,
        "static char **boot_prefix; static int boot_nprefix;",
        "#ifdef __LLVM_INSTR_PROFILE_GENERATE\n// PGO builds",
        r"""static char **boot_prefix; static int boot_nprefix;
int rt_relaunch(int nargs, char **args) {
    (void)nargs;
    (void)args;
    rt_log("[boot] guest requested process relaunch; PS5 frontend restart handoff is not implemented\n");
    return 0;
}

""",
    )

    replace_between_once(
        boot,
        "// rt_game.image bundled in the app:",
        "int main(int argc, char **argv) {",
        r"""// PS5 keeps the user's executable in the selected game directory.
// A future installer may provide a local private image, but there is no
// macOS application-bundle Resources lookup.
static int bundled_image(const char *argv0, char *out, size_t n) {
    (void)argv0;
    (void)out;
    (void)n;
    return 0;
}

""",
    )

    replace_once(
        boot,
        """    if (!isatty(2)) {   // launched from Finder or by Steam (not a terminal): keep a log file
        char log[PATH_MAX];
        snprintf(log, sizeof log, "%s/Library/Logs/%s.log", getenv("HOME") ? getenv("HOME") : "/tmp", rt_game.log_name);
        // keep the previous sessions' logs: a game that restarts itself spans several processes.
        // <log_name>.prev.log is the last one, .prev2 to .prev4 the ones before.
        int stem = (int)(strlen(log) - 4);
        char a[PATH_MAX], b[PATH_MAX];
        for (int k = 4; k >= 2; k--) {   // prev3 -> prev4, prev2 -> prev3, prev -> prev2
            if (k == 2) snprintf(a, sizeof a, "%.*s.prev.log", stem, log);
            else snprintf(a, sizeof a, "%.*s.prev%d.log", stem, log, k - 1);
            snprintf(b, sizeof b, "%.*s.prev%d.log", stem, log, k);
            rename(a, b);
        }
        char prev[PATH_MAX]; snprintf(prev, sizeof prev, "%.*s.prev.log", stem, log);
        rename(log, prev);
        freopen(log, "w", stderr);
    }
""",
        """    // Keep stderr attached to the PS5 process/logger. The PS5 frontend owns
    // persistent log rotation; boot.c must not invent macOS ~/Library paths.
""",
    )

    replace_once(
        boot,
        """    rt_init();
""",
        """    rt_init();
    // Native PS5 services must be ready before the guest image executes.
    // Keep the hook weak so public synthetic/runtime tests can link without
    // the registered-title frontend.
    extern int rt_ps5_frontend_init(void) __attribute__((weak));
    if (rt_ps5_frontend_init) {
        const int frontend_rc = rt_ps5_frontend_init();
        if (frontend_rc != 0) {
            rt_log("[boot] PS5 frontend initialization failed: %d\\n", frontend_rc);
            return 1;
        }
    }
""",
    )

    replace_once(
        boot,
        """    // absolute paths: the game chdirs into its folder before it ever relaunches
    boot_nprefix = dev ? 3 : 1;
    boot_prefix = calloc(4, sizeof *boot_prefix);
    for (int i = 0; i < boot_nprefix; i++) { char rp[PATH_MAX]; boot_prefix[i] = strdup(realpath(argv[i], rp) ? rp : argv[i]); }
""",
        """    // Process relaunch is delegated to the PS5 frontend, so no native
    // executable-prefix reconstruction is required here.
    boot_nprefix = 0;
    boot_prefix = NULL;
""",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runtime", type=Path)
    args = parser.parse_args()
    try:
        patch_boot(args.runtime)
    except (OSError, PatchError) as exc:
        parser.error(str(exc))
    print("PS5 Win64 boot.c core bootstrap edits applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
