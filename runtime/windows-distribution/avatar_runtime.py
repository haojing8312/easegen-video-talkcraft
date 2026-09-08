"""Relocatable offline avatar launcher. Inputs belong to the user, not the package."""
from pathlib import Path
import argparse
import os
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("check", "render"))
    parser.add_argument("--audio", default="")
    parser.add_argument("--avatar", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    engine = root / "engine"
    command = [str(engine / "py39/python.exe"), "-B", "-s",
               str(root / "adapter/heygem_win_onnx_bridge.py"),
               "--runtime-root", str(engine), "--gpu", str(args.gpu), "--timeout", str(args.timeout)]
    if args.mode == "check":
        command.append("--check")
    else:
        audio = Path(args.audio).resolve() if args.audio else root / "input/audio.wav"
        avatar = Path(args.avatar).resolve() if args.avatar else root / "input/avatar.mp4"
        output = Path(args.output).resolve() if args.output else root / "output/host.mp4"
        if not audio.is_file() or not avatar.is_file():
            print("Missing audio/avatar. Put your narration in input/audio.wav and your video in input/avatar.mp4.")
            return 2
        command += ["--audio", str(audio), "--avatar", str(avatar), "--output", str(output), "--batch-size", "1"]
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.call(command, cwd=root, env=env)


if __name__ == "__main__":
    sys.exit(main())
