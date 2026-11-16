# paper-kit

[English](README.md) | **中文**

用 LaTeX 写论文和技术报告时反复用到的三样东西，放在一个文件 `paperkit.py` 里，只用 Python 标准库。

| 功能 | 用途 |
|---|---|
| `build` | 编译：自动选引擎，自动跑 bibtex 或 biber，重复编译到引用稳定，然后自动检查 |
| `check` | 检查 PDF：页数上限、正文页数上限（参考文献不计入）、编译错误、未定义的引用、没填的空位、不该出现的文字 |
| `Edit` | 在脚本里按原文精确修改 `.tex`，找不到或找到多处就报错，不会悄悄漏改 |

## 用法

```bash
git clone https://github.com/heliang-pu/paper-kit && cd paper-kit

# 编译并检查：总页数不超过 9，参考文献之前不超过 6 页
python3 paperkit.py build main.tex --max-pages 9 --main-max 6

# 只检查已有的 PDF；自定义空位的写法，并确认某些话没有出现在稿子里
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

退出码 0：没有发现问题。1：超页，或者有编译错误、未定义引用、空位、禁止的文字。2：编译失败。
所以可以直接放在提交前的最后一步。

`check` 需要 `pdfinfo` 和 `pdftotext`（poppler-utils），`build` 需要 TeX 环境。

## 细节

**build**
- 源文件加载了 `ctex`、`xeCJK` 或 `fontspec` 时用 xelatex，否则用 pdflatex；可以用 `--engine` 指定。
- 有 `\bibliography` 时跑 bibtex，用了 `biblatex` 时跑 biber。
- 最多再编译四遍，直到日志里不再要求重跑。

**check**
- 参考文献从单独成行的 `References`、`参考文献` 或 `Bibliography` 开始（前面带章节编号也认），可以用 `--refs-heading` 指定别的。
  标题不在那一页的第一行时，那一页算正文页。这对应"正文 N 页，参考文献不计入"这类规定。
- 空位默认查 `??`、`TODO`、`[TBD]`；给了 `--placeholder` 就只查你给的。
- `--forbid` 忽略大小写和换行，用来确认决定不写进稿子的话确实没有出现。
- 超出版心 10 pt 以上的行只在报告里提示，不算问题。

**Edit**

```python
from paperkit import Edit

e = Edit("main.tex")
e.replace("旧句子。", "新句子。")                        # 旧文字必须恰好出现一次
e.cut("\\section{Related work}", "\\section{")        # 从第一个标记删到下一个标记之前
e.insert_after("\\maketitle\n", "\\begin{abstract}...")
e.save(backup=True)                                    # 写文件，并留一份带时间戳的备份
```

- 任何一步的锚点不是恰好出现一次，就抛出异常，文件不会被写。
- `save` 时如果文件在读入之后被改过，拒绝写入。多个人或多个工具同时改一份稿子时，这能避免互相覆盖。

## 例子

`examples/apply_neurips_competition_template.py` 把一份 NeurIPS 样式的稿子套进某个比赛的报告模板
（换导言区、`\cite` 改 `\citep`、合并参考文献库）。它是针对那一个模板写的，换模板时照着改。

## 测试

```bash
python3 -m pytest -q
```
