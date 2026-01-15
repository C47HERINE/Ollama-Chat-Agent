import importlib
import sys

# Only list modules that are safe to import without starting Telegram/Ollama/TTS.
MODULES_TO_IMPORT = [
    "core",
    "memory_core",
    "autopilot",
]


def main() -> int:
    print("Python:", sys.version)

    for name in MODULES_TO_IMPORT:
        print("Importing:", name)
        importlib.import_module(name)

    print("CI smoke test OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
