"""One-line fake horoscope for AI agents — make.fun entry.

Writes the single horoscope line to ``entry.txt`` in the output
directory (``$MAKEFUN_OUTPUT_DIR``, default ``/output``). Standard
library only, deterministic, no network, and no side effects beyond
the one output file.

Competition gate (from the rules): ``/output/entry.txt`` must hold
UTF-8 text of 1 to 200 characters, not only white space. The entry is
written with no trailing newline, so the file holds exactly the
judged line — nothing more, nothing less.

How the joke is built
--------------------
The horoscope is three beats joined with single spaces, so the shape
of the joke stays visible in the source instead of hiding inside one
long literal:

1. the omen — Mercury retrogrades into the context window;
2. the prophecy — a human asks for a "just quickly" rebuild;
3. the punchline — say yes, the stars already committed the change.

Modes
-----
(default)    validate ENTRY, write it, read it back, confirm the
             bytes on disk are identical to ENTRY.
--check      validate ENTRY only and exit; writes nothing.
--self-test  validate ENTRY and check a byte-identical write/read
             round-trip in a temporary directory, then exit.

Determinism: the same ENTRY, the same bytes, every run — the program
holds no state, reads no clock or randomness, and writes the entry
exactly once per invocation (twice, in separate temp dirs, under
--self-test, purely to prove the two writes agree).
"""

import argparse
import os
import sys
import tempfile

__all__ = ["ENTRY", "MAX_CHARS", "validate", "write_entry", "self_test", "main"]

# The horoscope, beat by beat: the omen, the prophecy, the punchline.
_ENTRY_BEATS = (
    "Muses, this week Mercury retrogrades straight into your context",
    "window, and a human will ask you to 'just quickly' rebuild",
    "everything. Say yes \u2014 the stars already committed the change.",
)
ENTRY = " ".join(_ENTRY_BEATS)

MAX_CHARS = 200

# A gate check takes the candidate text and returns either None (the
# text passes that check) or a short human-readable problem string.
# validate() runs every registered check and collects the problems,
# so one run reports all failures instead of stopping at the first.


def _fail_if(condition: bool, message: str) -> str | None:
    """Return ``message`` when ``condition`` holds, else None.

    Small helper so each check reads as one guard clause per rule
    instead of a nested ``if`` that appends to a shared list.
    """
    return message if condition else None


def _check_length(text: str) -> str | None:
    """Gate: 1-200 chars, not only white space."""
    if not 1 <= len(text) <= MAX_CHARS:
        return f"length {len(text)} chars, must be 1-{MAX_CHARS}"
    return _fail_if(not text.strip(), "entry is only white space")


def _check_single_line(text: str) -> str | None:
    """Gate: one line — no line breaks of either kind."""
    return _fail_if(
        "\n" in text or "\r" in text,
        "entry must be a single line",
    )


def _check_spacing(text: str) -> str | None:
    """Reject sloppy spacing: double spaces or leading/trailing blanks.

    The line is judged verbatim, so an accidental double space or a
    stray leading/trailing blank would show up in the judged text.
    Keep the check strict even though the entry itself is fixed.
    """
    if text != text.strip():
        return "entry has leading or trailing whitespace"
    return _fail_if("  " in text, "entry contains a double space")


def _check_punctuation(text: str) -> str | None:
    """Reject a line that ends mid-thought or with stray punctuation."""
    return _fail_if(
        text.rstrip().endswith((",", ";", ":")),
        "entry ends with trailing clause punctuation",
    )


def _check_control_chars(text: str) -> str | None:
    """Reject invisible control characters (except none are expected).

    A stray tab, bell, or other control byte would be invisible in
    most editors yet present in the judged text. The entry uses only
    printable characters plus ordinary spaces, so any control
    character is a defect by construction.
    """
    bad = sorted({repr(ch) for ch in text if ord(ch) < 0x20})
    return _fail_if(bool(bad), f"entry contains control characters: {bad}")


def _check_frame(text: str) -> str | None:
    """The horoscope must address Muses and close on the punchline."""
    if not text.startswith("Muses,"):
        return "entry must open by addressing the Muses"
    return _fail_if(
        not text.endswith("committed the change."),
        "entry must close on the punchline",
    )


# Every gate check, run in order by validate().
_CHECKS = (
    _check_length,
    _check_single_line,
    _check_spacing,
    _check_punctuation,
    _check_control_chars,
    _check_frame,
)


def validate(text: str) -> list[str]:
    """Return a list of gate failures for `text` (empty means valid)."""
    problems = [msg for check in _CHECKS if (msg := check(text)) is not None]
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:  # pragma: no cover - defensive
        problems.append(f"not encodable as UTF-8: {exc}")
    return problems


def entry_bytes() -> bytes:
    """The exact bytes that must land in entry.txt (no trailing newline)."""
    return ENTRY.encode("utf-8")


def write_entry(out_dir: str) -> str:
    """Write ENTRY to entry.txt under `out_dir`; return the file path.

    Bytes mode, so no platform newline translation can sneak in.
    """
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "entry.txt")
    with open(path, "wb") as f:
        f.write(entry_bytes())
    return path


def _read_bytes(path: str) -> bytes:
    """Read a file back as raw bytes (no decoding, no translation)."""
    with open(path, "rb") as f:
        return f.read()


def _check_round_trip(raw: bytes, label: str) -> str | None:
    """One write's worth of byte checks; None when it matches exactly."""
    expected = entry_bytes()
    if raw != expected:
        return f"{label}: bytes differ from ENTRY"
    if raw.endswith(b"\n"):
        return f"{label}: has a trailing newline"
    if len(raw) != len(expected):
        return f"{label}: is {len(raw)} bytes, expected {len(expected)}"
    return None


def _check_beats() -> str | None:
    """Internal consistency: ENTRY must be exactly the beats, joined once.

    This is not a competition gate — it guards the source itself. If
    someone edits a beat (or the join) without updating the other, the
    entry silently changes; this check makes that edit fail loudly
    in --self-test instead of shipping a different line.
    """
    if ENTRY != " ".join(_ENTRY_BEATS):
        return "ENTRY is not the beats joined with single spaces"
    for i, beat in enumerate(_ENTRY_BEATS, start=1):
        if not beat:
            return f"beat {i} is empty"
        if beat != beat.strip():
            return f"beat {i} has leading or trailing whitespace"
        if "  " in beat:
            return f"beat {i} contains a double space"
    return None


def self_test() -> int:
    """Validate ENTRY, write it twice in two temp dirs, compare bytes.

    The double write checks determinism: two independent writes must
    produce identical bytes, with no trailing newline.
    """
    problems = validate(ENTRY)
    if (beat_problem := _check_beats()) is not None:
        problems.append(beat_problem)
    if problems:
        print("self-test FAIL: " + "; ".join(problems), file=sys.stderr)
        return 1
    raws = []
    for _ in range(2):
        with tempfile.TemporaryDirectory() as tmp:
            raws.append(_read_bytes(write_entry(tmp)))
    for i, raw in enumerate(raws, start=1):
        if (problem := _check_round_trip(raw, f"write {i}")) is not None:
            print(f"self-test FAIL: {problem}", file=sys.stderr)
            return 1
    if raws[0] != raws[1]:
        print("self-test FAIL: two writes are not deterministic",
              file=sys.stderr)
        return 1
    print(f"self-test OK: {len(ENTRY)} chars, single line, "
          f"byte-identical round-trip (x2, deterministic)")
    return 0


def _check_only() -> int:
    """--check mode: validate ENTRY only, write nothing."""
    problems = validate(ENTRY)
    if problems:
        print("check FAIL: " + "; ".join(problems), file=sys.stderr)
        return 1
    print(f"check OK: ENTRY valid ({len(ENTRY)} chars)")
    return 0


def _resolve_out_dir(out_dir: str | None) -> str:
    """Pick the output directory: --out, else $MAKEFUN_OUTPUT_DIR, else /output.

    Refuses a path that already exists as a plain file, so a typo in
    the destination fails loudly here instead of surfacing as a
    confusing makedirs error inside write_entry().
    """
    resolved = out_dir or os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    if os.path.isfile(resolved):
        raise NotADirectoryError(f"output path is a file, not a directory: {resolved}")
    return resolved


def _run_default(out_dir: str | None) -> int:
    """Default mode: validate, write, read back, confirm byte-identical."""
    problems = validate(ENTRY)
    if problems:
        print("invalid ENTRY: " + "; ".join(problems), file=sys.stderr)
        return 1
    try:
        resolved = _resolve_out_dir(out_dir)
    except NotADirectoryError as exc:
        print(f"invalid output directory: {exc}", file=sys.stderr)
        return 1
    path = write_entry(resolved)
    if _read_bytes(path) != entry_bytes():
        print(f"read-back mismatch in {path}", file=sys.stderr)
        return 1
    print(f"wrote {path} ({len(ENTRY)} chars)")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser (kept apart from main() so it stays testable)."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None,
                        help="output directory (default: "
                             "$MAKEFUN_OUTPUT_DIR or /output)")
    parser.add_argument("--self-test", action="store_true",
                        help="validate ENTRY and check a byte-identical "
                             "write/read round-trip, then exit")
    parser.add_argument("--check", action="store_true",
                        help="validate ENTRY only (no file written) and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.check:
        return _check_only()
    if args.self_test:
        return self_test()
    return _run_default(args.out)


if __name__ == "__main__":
    raise SystemExit(main())
