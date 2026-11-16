from __future__ import annotations

from pathlib import Path
import shutil

import pytest

import paperkit

DOC = r"""\documentclass{article}
\begin{document}
\section{Introduction}
Hello~\cite{knuth}. See Section~\ref{sec:two}. %(EXTRA)
\section{Method}\label{sec:two}
Text.
\bibliographystyle{plain}
\bibliography{refs}
\end{document}
"""
BIB = "@book{knuth, author={Donald Knuth}, title={The TeXbook}, year={1984}, publisher={Addison-Wesley}}\n"

needs_tex = pytest.mark.skipif(not (shutil.which("pdflatex") and shutil.which("pdfinfo")), reason="no TeX / poppler")


def paper(tmp: Path, extra: str = "") -> Path:
    (tmp / "refs.bib").write_text(BIB)
    (tmp / "main.tex").write_text(DOC.replace("%(EXTRA)", extra))
    return tmp / "main.tex"


@needs_tex
def test_build_and_check(tmp_path, capsys):
    tex = paper(tmp_path)
    assert paperkit.main(["build", str(tex), "--max-pages", "1", "--main-max", "1"]) == 0
    out = capsys.readouterr().out
    assert "main.pdf: 1 pages" in out and "references start on page 1" in out and "0 errors, 0 undefined" in out
    assert "Knuth" in paperkit.page_texts(tmp_path / "main.pdf")[0]


@needs_tex
def test_check_finds_what_must_not_ship(tmp_path, capsys):
    long = "\\newpage More. " + r"\ref{nowhere} TODO \textbf{[E2]} first of 47 teams"
    tex = paper(tmp_path, long)
    code = paperkit.main(["build", str(tex), "--max-pages", "1", "--main-max", "1", "--placeholder", r"\[E[0-9]\]",
                          "--placeholder", "TODO", "--forbid", "47 teams"])  # fmt: skip
    out = capsys.readouterr().out
    assert code == 1
    assert "PROBLEM 2 pages, the limit is 1" in out
    assert "PROBLEM main content runs to page 2, the limit is 1" in out
    assert "PROBLEM 1 placeholders /\\[E[0-9]\\]/ left (pages [2])" in out
    assert "PROBLEM forbidden text '47 teams' on page [2]" in out
    assert "PROBLEM undefined references or citations: nowhere" in out


@needs_tex
def test_a_latex_error_is_reported(tmp_path, capsys):
    tex = paper(tmp_path, r"\undefinedmacro")
    assert paperkit.main(["build", str(tex)]) == 2
    assert "Undefined control sequence" in capsys.readouterr().err


def test_engine_choice():
    assert paperkit.engine_of("\\usepackage[UTF8]{ctex}") == "xelatex"
    assert paperkit.engine_of("% \\usepackage{ctex}\n\\usepackage{graphicx}") == "pdflatex"
    assert paperkit.engine_of("\\usepackage{amsmath,fontspec}") == "xelatex"


def test_edit_is_exact_and_all_or_nothing(tmp_path):
    path = tmp_path / "a.tex"
    path.write_text("one two two three\n\\section{A}\nbody\n\\section{B}\nend\n")
    e = paperkit.Edit(path)
    e.replace("one", "ONE").cut("\\section{A}", "\\section{", "").insert_after("three", "!")
    with pytest.raises(ValueError, match="found 2 times"):
        e.replace("two", "x")
    with pytest.raises(ValueError, match="found 0 times"):
        e.replace("absent", "x")
    assert path.read_text().startswith("one two")  # nothing written yet
    backup = e.save(backup=True)
    assert path.read_text() == "ONE two two three!\n\\section{B}\nend\n"
    assert backup.read_text().startswith("one two") and backup.name.startswith("a_before_")

    other = paperkit.Edit(path)
    other.replace("ONE", "1")
    path.write_text("someone else wrote this\n")
    with pytest.raises(RuntimeError, match="changed on disk"):
        other.save()
    assert path.read_text() == "someone else wrote this\n"
