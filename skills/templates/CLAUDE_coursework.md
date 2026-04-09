# CLAUDE.md — CUHK Coursework
# Place at: ~/coursework/CLAUDE.md

## IGSL v2 System
Skills and memory loaded via `~/.igsl-skills/hooks/session_start_v2.sh`.
Relevant skills: GEN-ERR-001 (LaTeX), META-05 (pipeline-builder)

## Project: CUHK Coursework Automation

## Coursework Rules

### Submission Standards
- Format: PDF via CUHK Blackboard
- Filename: `STUDENTID_COURSECODE_ASS#.pdf`
- LaTeX compiler: XeLaTeX preferred for Chinese support; pdflatex for pure English
- Always verify PDF opens correctly before submission

### LaTeX Workflow
```bash
# Compile with bibliography
xelatex main && biber main && xelatex main && xelatex main

# Check for errors
grep -E "^!" main.log | head -20

# Key packages for CUHK assignments:
# - amsmath, amssymb (math)
# - booktabs (tables)
# - hyperref (links, load last)
# - ctex or xeCJK (Chinese, XeLaTeX only)
```

### Assignment Checklist
- [ ] Correct filename convention
- [ ] Page numbers included
- [ ] References formatted (BibTeX/BibLaTeX)
- [ ] PDF compiles cleanly (0 errors, review warnings)
- [ ] File size reasonable (<10MB)

### LaTeX Error Quick Reference
```bash
# Get skill context for LaTeX errors:
python3 ~/.igsl-skills/skill.py load GEN-ERR-001
```

## Key Artifacts (memory)
```bash
python3 ~/.igsl-skills/memory/node.py query "coursework cuhk artifact"
```

## User Context
- igsl | CUHK undergraduate | coursework automation
- Style: concise, direct
