# paper-kit

**English** | [中文](README.zh-CN.md)

Three things that keep coming back when writing a paper or a technical report in LaTeX, in one file (`paperkit.py`),
standard library only.

| Part | Use |
|---|---|
| `build` | Compile: picks the engine, runs bibtex or biber, repeats until the references settle, then checks |
| `check` | Check the PDF: page limit, main-content limit with references excluded, LaTeX errors, undefined references, leftover placeholders, text that must not appear |
| `Edit` | Edit `.tex` files from a script by exact text, failing loudly instead of silently missing |

## Usage

```bash
git clone https://github.com/heliang-pu/paper-kit && cd paper-kit

# compile and check: at most 9 pages in all, at most 6 before the references
python3 paperkit.py build main.tex --max-pages 9 --main-max 6

# check an existing PDF; name your own placeholders, and make sure some phrases are not in it
python3 paperkit.py check main.pdf --main-max 6 \
    --placeholder '\[E[0-9]\]' --placeholder 'TODO' --forbid 'internal codename'
```

```
main.pdf: 7 pages
references start on page 6, text line 31 of 52; main content ends on page 6
4321 words
log: 0 errors, 0 undefined, 0 overfull boxes (0 of 10 pt or more)
PROBLEM 3 placeholders /\[E[0-9]\]/ left (pages [2, 4])
```

Exit code 0: nothing found. 1: a limit is broken, or there is a LaTeX error, an undefined reference, a placeholder or
a forbidden text. 2: the build failed. That makes it usable as the last step before a submission.

Needs `pdfinfo` and `pdftotext` (poppler-utils) for `check`, and a TeX installation for `build`.

## Details

**build**
- xelatex when the source loads `ctex`, `xeCJK` or `fontspec`, otherwise pdflatex; `--engine` overrides.
- bibtex when the source has `\bibliography`, biber when it uses `biblatex`.
- Up to four more passes, until the log no longer asks for a rerun.

**check**
- The references start at a line that is exactly `References`, `参考文献` or `Bibliography` (a section number in
  front is accepted); `--refs-heading` names another. If the heading is not the first line of its page, that page
  counts as main content. This is the rule of venues that say "N pages of main content, references excluded".
- Placeholders default to `??`, `TODO` and `[TBD]`; with `--placeholder` only yours are looked for.
- `--forbid` ignores case and line breaks. Use it to confirm that something you decided not to write is really gone.
- Lines that stick out by 10 pt or more are reported, not counted as problems.

**Edit**

```python
from paperkit import Edit

e = Edit("main.tex")
e.replace("An old sentence.", "A new sentence.")      # the old text must occur exactly once
e.cut("\\section{Related work}", "\\section{")        # from the first marker up to the next one
e.insert_after("\\maketitle\n", "\\begin{abstract}...")
e.save(backup=True)                                    # writes the file and keeps a time-stamped copy
```

- If any anchor does not occur exactly once, an exception is raised and nothing is written.
- `save` refuses to write when the file changed on disk after it was read. With several people (or several tools)
  editing one draft, this is what stops them from overwriting each other.

## Example

`examples/apply_neurips_competition_template.py` moves a NeurIPS-style draft into a competition's report template
(new preamble, `\cite` to `\citep`, merged bibliography). It was written for that one template; adapt it for another.

## Tests

```bash
python3 -m pytest -q
```
