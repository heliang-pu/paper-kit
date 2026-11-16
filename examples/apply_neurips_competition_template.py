#!/usr/bin/env python3
"""Put the standalone workshop paper into the organizers' report template (RoboSynChallenge-2026-submission-template).

    python3 apply_official_template.py <source.tex> <out_dir> [--template <dir>] [--refs <refs.bib>] [--keep-spacing]

What changes, and nothing else:
  * preamble: the template's (\\usepackage[final]{neurips_2026}, footer "RoboSynChallenge 2026", hyperref hidelinks);
    the paper's own packages and macros are kept below it;
  * citations: \\cite -> \\citep (the template uses plainnat, author-year); the competition is cited with the
    template's entry `robosynchallenge`;
  * bibliography: \\bibliographystyle{plainnat} + references.bib (the template's entry + the paper's refs.bib);
  * title, authors, sections and text are copied unchanged.
The source file is not modified. The script stops without writing if an expected line is missing.
"""

import argparse
import pathlib
import re
import shutil

TEMPLATE_PREAMBLE = r"""\documentclass{article}

% ----- From the official template (RoboSynChallenge-2026-submission-template/main.tex) -----
% Put the official neurips_2026.sty beside this file.
% Use the unnumbered NeurIPS layout with the competition notice.
\usepackage[final]{neurips_2026}
\makeatletter
\renewcommand{\@noticestring}{RoboSynChallenge 2026}
\makeatother
\usepackage[T1]{fontenc}
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage[hidelinks]{hyperref}

% ----- This report's own packages and macros -----
"""

# Preamble lines of the source that the template replaces.
DROP = [
    r"\\documentclass\{article\}",
    r"\\usepackage\[[^\]]*\]\{neurips_2026\}",
    r"\\workshoptitle\{.*\}",
    r"\\usepackage\[T1\]\{fontenc\}",
    r"\\usepackage\{hyperref\}",
    r"\\usepackage\{booktabs\}",
    r"\\usepackage\{graphicx\}",
    r"\\definecolor\{linkblue\}.*",
    r"\\hypersetup\{.*\}",
    r"% Standalone English workshop paper.*",
    r"% Build: .*",
    r"% It does not depend on .*",
]
# Spacing changes made to fit six pages with the references; the template leaves the style's spacing alone.
SPACING = [
    r"\\setlength\{\\textfloatsep\}.*",
    r"\\setlength\{\\floatsep\}.*",
    r"\\setlength\{\\abovecaptionskip\}.*",
    r"\\setlength\{\\belowcaptionskip\}.*",
    r"\\raggedbottom",
]
OLD_KEY, NEW_KEY = "robosyn", "robosynchallenge"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("out_dir")
    here = pathlib.Path(__file__).resolve().parent
    ap.add_argument("--template", default=str(here.parent / "RoboSynChallenge-2026-submission-template"))
    ap.add_argument("--refs", default=None, help="the paper's .bib (default: refs.bib beside the source)")
    ap.add_argument("--keep-spacing", action="store_true", help="keep the float and caption spacing of the source")
    args = ap.parse_args()

    src = pathlib.Path(args.source).resolve()
    out = pathlib.Path(args.out_dir).resolve()
    tpl = pathlib.Path(args.template).resolve()
    refs = pathlib.Path(args.refs).resolve() if args.refs else src.parent / "refs.bib"
    text = src.read_text(encoding="utf-8")

    # --- split at \title ---
    m = re.search(r"^(?:% Title history.*\n(?:%.*\n)*)?\\title\{", text, flags=re.M)
    assert m, "no \\title in the source"
    pre, body = text[: m.start()], text[m.start() :]

    # --- preamble ---
    drop = DROP + ([] if args.keep_spacing else SPACING)
    kept, dropped = [], []
    for line in pre.split("\n"):
        if any(re.fullmatch(p, line.strip()) for p in drop):
            dropped.append(line)
        else:
            kept.append(line)
    assert any("neurips_2026" in d for d in dropped), "the source does not load neurips_2026"
    own = "\n".join(kept).strip("\n") + "\n\n"

    # --- citations ---
    def cite(mm):
        keys = [NEW_KEY if k.strip() == OLD_KEY else k.strip() for k in mm.group(1).split(",")]
        return r"\citep{" + ",".join(keys) + "}"

    body, n_cite = re.subn(r"\\cite\{([^}]*)\}", cite, body)
    assert n_cite > 0, "no \\cite in the source"

    # --- bibliography ---
    body, n1 = re.subn(r"\\bibliographystyle\{[^}]*\}", lambda _: r"\bibliographystyle{plainnat}", body)
    body, n2 = re.subn(r"^.*\\bibliography\{[^}]*\}.*$", lambda _: r"\bibliography{references}", body, flags=re.M)
    assert (n1, n2) == (1, 1), ("bibliography lines", n1, n2)

    # --- references.bib: the template's entry + the paper's entries (without its own entry for the competition) ---
    tpl_bib = (tpl / "references.bib").read_text(encoding="utf-8").strip()
    assert "@misc{" + NEW_KEY + "," in tpl_bib
    own_bib = refs.read_text(encoding="utf-8")
    own_bib, n_old = re.subn(r"@misc\{" + OLD_KEY + r",.*?\n\}\n", "", own_bib, count=1, flags=re.S)
    assert n_old == 1, "the paper's refs.bib has no entry '%s'" % OLD_KEY
    bib = (
        "% The competition entry comes from the official template; the rest is the paper's refs.bib.\n"
        + tpl_bib
        + "\n\n"
        + own_bib.strip()
        + "\n"
    )

    # --- write ---
    out.mkdir(parents=True, exist_ok=True)
    (out / "main.tex").write_text(TEMPLATE_PREAMBLE + own + body, encoding="utf-8")
    (out / "references.bib").write_text(bib, encoding="utf-8")
    shutil.copy2(tpl / "neurips_2026.sty", out / "neurips_2026.sty")
    deps = re.findall(r"\\input\{([^}]*)\}", body) + re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]*)\}", body)
    copied = []
    for d in deps:
        p = src.parent / d
        if not p.exists() and (src.parent / (d + ".tex")).exists():
            p, d = src.parent / (d + ".tex"), d + ".tex"
        assert p.exists(), "missing file: %s" % d
        (out / d).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, out / d)
        copied.append(d)
    print("wrote", out / "main.tex")
    print("  citations converted:", n_cite)
    print("  preamble lines replaced by the template:", len([d for d in dropped if d.strip()]))
    print("  files copied:", ", ".join(copied))


if __name__ == "__main__":
    main()
