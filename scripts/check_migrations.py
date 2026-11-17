"""CI guard: a migration graph must have exactly one head."""

from alembic.config import Config
from alembic.script import ScriptDirectory


def check_heads(config: Config) -> str:
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise ValueError(f"Expected exactly one Alembic head; found {len(heads)}: {heads}")
    return heads[0]


if __name__ == "__main__":
    try:
        print(check_heads(Config("alembic.ini")))
    except ValueError as error:
        raise SystemExit(str(error)) from None
