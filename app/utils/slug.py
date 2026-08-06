import re


def slugify(value: str) -> str:

    value = value.lower()

    value = re.sub(
        r"[^a-z0-9]+",
        "-",
        value,
    )

    value = value.strip("-")

    return value