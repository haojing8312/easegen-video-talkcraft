#!/usr/bin/env python3
"""Invoke Easegen's audited DH_live CPU adapter from an isolated runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--easegen-root", required=True)
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--runtime-python", required=True)
    parser.add_argument("--avatars-root", required=True)
    parser.add_argument("--avatar-code", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("--expected-commit", default="")
    args = parser.parse_args()

    easegen_root = Path(args.easegen_root).resolve()
    sys.path.insert(0, str(easegen_root))
    try:
        from utils.digital_human.dh_live import DHLiveConfig, render_dh_live_video

        generated = Path(render_dh_live_video(
            args.avatar_code,
            args.audio,
            DHLiveConfig(
                runtime_root=Path(args.runtime_root),
                python_executable=args.runtime_python,
                avatars_root=Path(args.avatars_root),
                output_root=Path(args.output_root),
                timeout_seconds=args.timeout,
                expected_commit=args.expected_commit,
            ),
        )).resolve()
        output = Path(args.out).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        if generated != output:
            shutil.copy2(generated, output)
        print(json.dumps({"success": True, "output": str(output)}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"success": False, "type": type(exc).__name__, "error": str(exc)},
                         ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
