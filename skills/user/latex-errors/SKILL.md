# GEN-ERR-001 — LaTeX Error Patterns
**id**: GEN-ERR-001 | **hardness**: soft-hook | **type**: skill

## Purpose
Diagnose and fix common LaTeX compilation errors quickly. Pattern library for pdflatex, xelatex, lualatex.

## Trigger Keywords
`latex`, `pdflatex`, `xelatex`, `compilation error`, `undefined control sequence`, `missing $`, `overfull`, `bibtex`, `biblatex`, `beamer`, `tikz`

## Common Errors & Fixes

### Undefined control sequence
```
! Undefined control sequence.
l.42 \somecmd
```
**Fix**: Missing package or typo. Check: `\usepackage{pkg}` for `\somecmd`. Run `texdoc pkg`.

### Missing $ inserted
```
! Missing $ inserted.
```
**Fix**: Math mode required. Wrap in `$...$` or `\(...\)`. Often caused by `_` or `^` outside math.

### File not found
```
! LaTeX Error: File 'foo.sty' not found.
```
**Fix**: Install with `tlmgr install foo` or check spelling.

### Overfull \hbox
```
Overfull \hbox (12.3pt too wide) in paragraph
```
**Fix**: Not fatal. Options: `\sloppy`, `\linebreak`, rewrite sentence, use `microtype` package.

### Package conflict (option clash)
```
! LaTeX Error: Option clash for package foo.
```
**Fix**: `\usepackage{foo}` called twice with different options. Load package once with all options, or use `\PassOptionsToPackage{opt}{foo}` before `\documentclass`.

### Too many open files
```
! TeX capacity exceeded, sorry [input stack size=...]
```
**Fix**: Circular `\input{}` or too many nested files. Check for circular references.

### Hyperref must be last
```
! Package hyperref Error: Wrong driver...
```
**Fix**: `\usepackage{hyperref}` must be the last `\usepackage` call (with few exceptions: `cleveref` after).

### Font not found (XeLaTeX/LuaLaTeX)
```
Font "FontName" not found
```
**Fix**: `fc-list | grep "FontName"` to verify installed. Use exact name from fc-list output.

### BibTeX/BibLaTeX not running
**Symptom**: `[?]` citations, "I found no \citation commands"
**Fix**: Run sequence: `pdflatex → bibtex/biber → pdflatex → pdflatex`

### Beamer overlay spec error
```
! Package pgf Error: ...
```
**Fix**: Overlay spec `<1->` syntax requires `fragile` option on frames with verbatim: `\begin{frame}[fragile]`

## Package Reference
| Need | Package |
|------|---------|
| Math | `amsmath`, `amssymb` |
| Tables | `booktabs`, `longtable`, `tabularx` |
| Code | `listings`, `minted` |
| Figures | `graphicx`, `subfig`, `caption` |
| Links | `hyperref` (load last) |
| Better spacing | `microtype` |
| Chinese | `ctex` (XeLaTeX), `CJKutf8` (pdflatex) |
| Colors | `xcolor` |
| Drawing | `tikz`, `pgfplots` |

## Compilation Commands
```bash
# Standard
pdflatex -interaction=nonstopmode main.tex

# With bibliography
pdflatex main && bibtex main && pdflatex main && pdflatex main

# With biblatex/biber
pdflatex main && biber main && pdflatex main && pdflatex main

# XeLaTeX (for fonts/CJK)
xelatex -interaction=nonstopmode main.tex

# Check log for errors only
grep -E "^!" main.log | head -20
```

## Rules
- `\input{}` for sub-files (no page break); `\include{}` adds page break + allows `\includeonly`
- `hyperref` always last (or second-to-last if using `cleveref`)
- Always run pdflatex twice after adding new `\label`/`\ref` pairs
- For CUHK submissions: check required font (usually Times or Computer Modern)
