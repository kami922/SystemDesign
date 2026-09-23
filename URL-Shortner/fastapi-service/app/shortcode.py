_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_BASE = len(_ALPHABET)


def encode(n: int) -> str:
    if n == 0:
        return _ALPHABET[0]
    digits = []
    while n > 0:
        n, rem = divmod(n, _BASE)
        digits.append(_ALPHABET[rem])
    return "".join(reversed(digits))
