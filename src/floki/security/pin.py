from __future__ import annotations

import sys

import bcrypt


def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_pin(pin: str, pin_hash: str) -> bool:
    if not pin_hash:
        return False
    try:
        return bcrypt.checkpw(pin.encode("utf-8"), pin_hash.encode("utf-8"))
    except ValueError:
        return False


def _cli() -> None:
    if len(sys.argv) != 3 or sys.argv[1] != "hash":
        print("usage: python -m floki.security.pin hash <pin>", file=sys.stderr)
        sys.exit(2)
    print(hash_pin(sys.argv[2]))


if __name__ == "__main__":
    _cli()
