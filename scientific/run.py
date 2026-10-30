"""Exact frozen formatting/SQL helpers; unrelated historical runner omitted."""
import re
import time

def code_blocks(text):
    return [
        b.strip("\n") for b in re.findall(r"```[a-zA-Z0-9_+-]*\n(.*?)```", text, re.S)
    ]


def norm_rows(rows):
    return [tuple(round(v, 6) if isinstance(v, float) else v for v in r) for r in rows]


def sql_rows(setup, query):
    """Run one read-only query on an in-memory SQLite database built from `setup`; returns the rows (raises on error or after 5 s)."""
    import sqlite3

    con = sqlite3.connect(":memory:")
    try:
        con.executescript(setup)
        ok = {
            sqlite3.SQLITE_SELECT,
            sqlite3.SQLITE_READ,
            sqlite3.SQLITE_FUNCTION,
            sqlite3.SQLITE_RECURSIVE,
        }
        con.set_authorizer(
            lambda action, *a: (
                sqlite3.SQLITE_OK if action in ok else sqlite3.SQLITE_DENY
            )
        )
        t0 = time.time()
        con.set_progress_handler(lambda: 1 if time.time() - t0 > 5 else 0, 100000)
        return norm_rows(con.execute(query).fetchall())
    finally:
        con.close()


def sql_check(setup, expected, ordered, answer):
    blocks = code_blocks(answer)
    query = (blocks[0] if blocks else answer).strip()
    try:
        got = sql_rows(setup, query)
    except Exception as e:
        return False, f"the query fails: {type(e).__name__}: {e}"
    want = norm_rows(expected)
    if not ordered:
        got, want_c = sorted(got, key=repr), sorted(want, key=repr)
    else:
        want_c = want
    if got == want_c:
        return True, "rows match"
    return (
        False,
        f"returned {got[:6]!r}{' ...' if len(got) > 6 else ''} ({len(got)} rows), expected {want[:6]!r}{' ...' if len(want) > 6 else ''} ({len(want)} rows)",
    )
