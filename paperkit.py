#!/usr/bin/env python3
"""paper-kit: build a LaTeX paper and check it against a page limit; edit .tex files without silent misses.

    paperkit.py build main.tex [--max-pages 6] [--main-max 6] [--refs-heading References]
    paperkit.py check main.pdf [--log main.log] [--max-pages 6] [--main-max 6] [--refs-heading References]
                               [--placeholder '\\[E[0-9]\\]'] [--forbid '47 teams']

build   picks the engine from the source (xelatex when it loads ctex / xeCJK / fontspec, else pdflatex), runs bibtex or
        biber when the source asks for one, repeats until the references settle, then runs check.
check   pages; where the references start (so "N pages of main content, references excluded" can be checked);
        LaTeX errors, undefined references and citations, overfull boxes of 10 pt or more; leftover placeholders
        (default: "??", "TODO", "[TBD]"); and any --forbid text that must not appear in the PDF.
        Exit code 1 when a limit is broken or an error, undefined reference, placeholder or forbidden text is found.

In a script, ``from paperkit import Edit`` gives exact-string edits that fail loudly:

    e = Edit("main.tex")
    e.replace("old sentence.", "new sentence.")      # the old text must occur exactly once
    e.cut("\\\\section{Related work}", "\\\\section{", "")   # from the first marker up to the next one
    e.save(backup=True)                               # nothing is written unless every edit applied

Standard library only. Needs pdfinfo and pdftotext (poppler-utils) for check, and a TeX installation for build.
"""

from __future__ import annotations

import argparse
import datetime
from pathlib import Path
import re
import shutil
import subprocess
import sys

DEFAULT_PLACEHOLDERS = [r"\?\?", r"\bTODO\b", r"\[TBD\]"]
REFS_HEADINGS = ["References", "参考文献", "Bibliography"]


class Edit:
    """Exact-string edits of one text file. Every edit asserts that its anchor is there exactly once."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.original = self.path.read_text(encoding="utf-8")
        self.text = self.original
        self.count = 0

    def _once(self, anchor: str) -> int:
        found = self.text.count(anchor)
        if found != 1:
            raise ValueError(f"{self.path}: expected once, found {found} times: {anchor[:70]!r}")
        return self.text.index(anchor)

    def replace(self, old: str, new: str) -> "Edit":
        start = self._once(old)
        self.text = self.text[:start] + new + self.text[start + len(old) :]
        self.count += 1
        return self

    def cut(self, start: str, end: str, new: str = "") -> "Edit":
        """Replace from ``start`` (kept out) up to, not including, the next ``end`` after it."""
        a = self._once(start)
        b = self.text.find(end, a + len(start))
        if b < 0:
            raise ValueError(f"{self.path}: no {end[:50]!r} after {start[:50]!r}")
        self.text = self.text[:a] + new + self.text[b:]
        self.count += 1
        return self

    def insert_before(self, anchor: str, new: str) -> "Edit":
        return self.replace(anchor, new + anchor)

    def insert_after(self, anchor: str, new: str) -> "Edit":
        return self.replace(anchor, anchor + new)

    def save(self, backup: bool = False) -> Path | None:
        """Write the file; refuse if it changed on disk since it was read (someone else is editing it)."""
        if self.path.read_text(encoding="utf-8") != self.original:
            raise RuntimeError(f"{self.path} changed on disk since it was read; nothing written")
        copy = None
        if backup and self.text != self.original:
            copy = self.path.with_name(
                f"{self.path.stem}_before_{datetime.datetime.now():%Y%m%d_%H%M%S}{self.path.suffix}"
            )
            shutil.copy2(self.path, copy)
        self.path.write_text(self.text, encoding="utf-8")
        self.original = self.text
        return copy


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, errors="replace")


def engine_of(source: str) -> str:
    body = re.sub(r"(?<!\\)%.*", "", source)
    return (
        "xelatex"
        if re.search(r"\\usepackage(\[[^\]]*\])?\{[^}]*\b(ctex|xeCJK|fontspec)\b", body) or "{ctexart}" in body
        else "pdflatex"
    )


def build(tex: Path, engine: str | None = None) -> Path:
    """Compile until the references settle; the PDF's path. Raises RuntimeError with the first LaTeX error."""
    tex = Path(tex).resolve()
    source = tex.read_text(encoding="utf-8", errors="replace")
    engine = engine or engine_of(source)
    body = re.sub(r"(?<!\\)%.*", "", source)
    latex = [engine, "-interaction=nonstopmode", "-halt-on-error", tex.name]
    first = run(latex, tex.parent)
    if first.returncode != 0:
        errors = re.findall(r"^!.*(?:\n.*){0,2}", first.stdout, re.M)
        raise RuntimeError(f"{engine} failed on {tex.name}:\n" + (errors[0] if errors else first.stdout[-600:]))
    if re.search(r"\\(bibliography|addbibresource)\{", body):
        tool = (
            ["biber", tex.stem] if re.search(r"\\usepackage(\[[^\]]*\])?\{biblatex\}", body) else ["bibtex", tex.stem]
        )
        done = run(tool, tex.parent)
        if done.returncode != 0 and "error message" in done.stdout:
            raise RuntimeError(f"{tool[0]} failed:\n{done.stdout[-600:]}")
    for _ in range(4):
        done = run(latex, tex.parent)
        if done.returncode != 0:
            raise RuntimeError(f"{engine} failed on {tex.name}:\n{done.stdout[-600:]}")
        if "Rerun to get" not in done.stdout and "Label(s) may have changed" not in done.stdout:
            break
    return tex.with_suffix(".pdf")


def page_texts(pdf: Path) -> list[str]:
    info = run(["pdfinfo", str(pdf)], pdf.parent).stdout
    pages = int(re.search(r"Pages:\s+(\d+)", info).group(1))
    return [
        run(["pdftotext", "-f", str(p), "-l", str(p), "-layout", str(pdf), "-"], pdf.parent).stdout
        for p in range(1, pages + 1)
    ]


def check(pdf: Path, log: Path | None = None, max_pages: int | None = None, main_max: int | None = None,
          refs_heading: str | None = None, placeholders: list[str] | None = None, forbid: list[str] | None = None) -> tuple[list[str], list[str]]:  # fmt: skip
    """(report lines, problems)."""
    pdf = Path(pdf).resolve()
    texts = page_texts(pdf)
    report, problems = [f"{pdf.name}: {len(texts)} pages"], []
    if max_pages is not None and len(texts) > max_pages:
        problems.append(f"{len(texts)} pages, the limit is {max_pages}")

    headings = [refs_heading] if refs_heading else REFS_HEADINGS
    refs_page = refs_line = None
    for number, text in enumerate(texts, 1):
        lines = [line for line in text.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            if line.strip() in headings or re.fullmatch(
                r"\d+(\.\d+)*\s+(" + "|".join(map(re.escape, headings)) + ")", line.strip()
            ):
                refs_page, refs_line, total = number, index, len(lines)
        if refs_page:
            break
    if refs_page:
        main_pages = refs_page if refs_line > 0 else refs_page - 1
        report.append(
            f"references start on page {refs_page}, text line {refs_line + 1} of {total}; main content ends on page {main_pages}"
        )
        if main_max is not None and main_pages > main_max:
            problems.append(f"main content runs to page {main_pages}, the limit is {main_max}")
    else:
        report.append(f"no references heading found ({', '.join(headings)})")
        if main_max is not None:
            problems.append("cannot check the main-content limit: no references heading found (--refs-heading)")

    everything = "\n".join(texts)
    for pattern in placeholders if placeholders is not None else DEFAULT_PLACEHOLDERS:
        hits = [(n, m.group(0)) for n, text in enumerate(texts, 1) for m in re.finditer(pattern, text)]
        if hits:
            problems.append(f"{len(hits)} placeholders /{pattern}/ left (pages {sorted({n for n, _ in hits})})")
    for text in forbid or []:
        pages = [n for n, page in enumerate(texts, 1) if text.lower() in re.sub(r"\s+", " ", page).lower()]
        if pages:
            problems.append(f"forbidden text {text!r} on page {pages}")
    report.append(f"{len(everything.split())} words")

    log = Path(log) if log else pdf.with_suffix(".log")
    if log.exists():
        text = log.read_text(errors="replace")
        errors = re.findall(r"^! .*", text, re.M)
        undefined = sorted(set(re.findall(r"(?:Reference|Citation) `([^']+)' on page \d+ undefined", text)))
        overfull = [float(x) for x in re.findall(r"Overfull \\hbox \(([\d.]+)pt too wide\)", text)]
        wide = [x for x in overfull if x >= 10]
        report.append(
            f"log: {len(errors)} errors, {len(undefined)} undefined, {len(overfull)} overfull boxes ({len(wide)} of 10 pt or more)"
        )
        if errors:
            problems.append(f"LaTeX errors: {errors[0]}")
        if undefined:
            problems.append(f"undefined references or citations: {', '.join(undefined[:8])}")
        if wide:
            report.append(f"widest overfull box: {max(wide):.0f} pt")
    else:
        report.append(f"no log at {log.name}")
    return report, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "check"):
        p = sub.add_parser(name)
        p.add_argument("file", type=Path, help="main.tex" if name == "build" else "main.pdf")
        p.add_argument("--max-pages", type=int, help="limit on all pages")
        p.add_argument("--main-max", type=int, help="limit on the pages before the references")
        p.add_argument(
            "--refs-heading", help="the references' heading as printed (default: References, 参考文献, Bibliography)"
        )
        p.add_argument(
            "--placeholder", action="append", help="regex of a leftover placeholder (repeatable; replaces the defaults)"
        )
        p.add_argument("--forbid", action="append", help="text that must not appear in the PDF (repeatable)")
        if name == "build":
            p.add_argument("--engine", choices=["pdflatex", "xelatex", "lualatex"])
        else:
            p.add_argument("--log", type=Path)
    args = parser.parse_args(argv)
    try:
        pdf = build(args.file, args.engine) if args.command == "build" else args.file
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 2
    report, problems = check(pdf, getattr(args, "log", None), args.max_pages, args.main_max, args.refs_heading,
                             args.placeholder, args.forbid)  # fmt: skip
    print("\n".join(report))
    for problem in problems:
        print(f"PROBLEM {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
