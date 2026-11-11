#!/usr/bin/env python3
# Status line opcional: `ctx NN% · cache: hit NN% Nm|frío`. Uso: statusline.py [--wrap '<comando>'].
# Con --wrap ejecuta ese comando con el mismo stdin (sin shell, 2 s) y añade el segmento tras su salida.
# Lee el JSON de forma defensiva: un campo ausente omite su segmento; nunca falla (exit 0).
# Campos: context_window.used_percentage; prompt_cache.{warm, hit_ratio, misses, expires_at, caching_observed}.
import contextlib
import json
import shlex
import subprocess
import sys
import time


def num(d, key):
    v = d.get(key) if isinstance(d, dict) else None
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def segment(data, now):
    parts = []
    pct = num(data.get("context_window"), "used_percentage")
    if pct is not None:
        parts.append(f"ctx {pct:.0f}%")
    cache = data.get("prompt_cache")
    if isinstance(cache, dict) and cache.get("caching_observed") is not False and isinstance(cache.get("warm"), bool):
        if not cache["warm"]:
            parts.append("cache: frío")
        else:
            ratio, expires, misses = num(cache, "hit_ratio"), num(cache, "expires_at"), num(cache, "misses")
            text = "caliente" if ratio is None else f"hit {round(ratio * 100)}%"
            if misses:
                text += f" miss {misses:.0f}"
            if expires is not None:
                text += f" {max(0, (expires - now) // 60):.0f}m"
            parts.append(f"cache: {text}")
    return " · ".join(parts)


def main(argv):
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
        seg = segment(data, time.time()) if isinstance(data, dict) else ""
    except ValueError:
        seg = ""
    base = ""
    if len(argv) == 3 and argv[1] == "--wrap":
        with contextlib.suppress(OSError, ValueError, subprocess.SubprocessError):
            cmd = shlex.split(argv[2])
            run = subprocess.run(cmd, input=raw, capture_output=True, text=True, timeout=2, check=False)
            base = run.stdout.rstrip("\n")
    print(" ".join(p for p in (base, seg) if p))


if __name__ == "__main__":
    with contextlib.suppress(Exception):
        main(sys.argv)
