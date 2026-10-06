## MANDATORY INFOGRAPHIC GENERATION AND NOTEBOOK INTEGRATION (CODE-DRAWN)

The final notebook must contain exactly three learner-ready infographic images embedded inside the `.ipynb`. Do NOT use any AI image-generation tool (DALL-E, Nano Banana, Gemini image, etc.). Instead, DRAW each infographic deterministically with `matplotlib` inside the code interpreter, so every label is exact and QA-safe, then base64-embed it. This avoids garbled text and any image-tool-to-code handoff.

### Visual chunking

After the lesson content is drafted, divide the complete learning-material portion into exactly three logically distinct semantic visual chunks based on topic flow and conceptual grouping. This is independent of whether the notebook uses 3 or 4 teaching concept groups. For each chunk internally determine: a concise learner-facing title, the 2-4 concept "cards" it needs, the short exact labels inside each card, an optional one-line takeaway, and the exact existing Concept Cell A where it will be placed. Every supplied topic must be represented across the three infographics; do not force an unrelated concept in for symmetry.

### Drawing rules (exact-text, QA-safe)

- Use `matplotlib` (always available; no install). Only use `graphviz` if a node-graph layout is clearly better, with a `try/except ImportError` install.
- Every word, label, symbol, and code snippet drawn in the image must be copied verbatim from the validated lesson content: correct spelling, standard terminology, correct categorization. Never place a concept in the wrong group.
- Favor visuals over text: colored cards/nodes, flow arrows, clear grouping, short labels only. No paragraphs inside the image.
- Use a professional multicolored palette with strong contrast (deep blue, emerald green, warm accent on a clean light background) and a clear hierarchy: banner title -> card headers -> concise key points.
- Render landscape at 1600 x 900 or larger. Keep text non-overlapping, readable, and uncluttered.

### Helper code to use inside the code interpreter

Define and use these helpers (adapt content per lesson):

```python
import base64, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

PALETTE = ["#0065BD", "#2E7D5B", "#E08A1E", "#6C4AB6"]
BG, INK, TITLEBG = "#F5F7FA", "#1B2733", "#0B3D63"

def _fit_fontsize(text, base, max_chars):
    # shrink long labels so they never clip/overflow their box
    if len(text) <= max_chars:
        return base
    return max(8.5, base * max_chars / len(text))

def make_infographic(title, cards, out_png, footer=None):
    # title: str ; cards: list of {"head": str, "points": [str, ...]} ; footer: optional str
    n = len(cards)
    fig = plt.figure(figsize=(16, 9), dpi=100)      # -> exactly 1600x900 px
    ax = fig.add_axes([0, 0, 1, 1])                 # full-bleed = guaranteed dimensions
    fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")
    ax.add_patch(FancyBboxPatch((3, 87), 94, 9, boxstyle="round,pad=0.6,rounding_size=2", fc=TITLEBG, ec="none"))
    ax.text(50, 91.5, title, ha="center", va="center", color="white",
            fontsize=_fit_fontsize(title, 25, 46), fontweight="bold")
    margin, gap = 4, 3
    card_w = (100 - 2*margin - gap*(n-1)) / n
    card_h, card_y = 55, 20
    for i, card in enumerate(cards):
        color = PALETTE[i % len(PALETTE)]
        x = margin + i*(card_w + gap)
        ax.add_patch(FancyBboxPatch((x, card_y), card_w, card_h, boxstyle="round,pad=0.4,rounding_size=2", fc="white", ec=color, lw=2.2))
        ax.add_patch(FancyBboxPatch((x, card_y+card_h-11), card_w, 11, boxstyle="round,pad=0.4,rounding_size=2", fc=color, ec="none"))
        ax.add_patch(plt.Circle((x+4.2, card_y+card_h-5.5), 2.2, color="white"))
        ax.text(x+4.2, card_y+card_h-5.5, str(i+1), ha="center", va="center", color=color, fontsize=12, fontweight="bold")
        ax.text(x+card_w/2+2, card_y+card_h-5.5, card["head"], ha="center", va="center",
                color="white", fontsize=_fit_fontsize(card["head"], 14, 20), fontweight="bold")
        py = card_y + card_h - 17
        for p in card["points"]:
            ax.plot(x+3.2, py, marker="o", ms=5.5, color=color)
            ax.text(x+5.8, py, p, ha="left", va="center", color=INK,
                    fontsize=_fit_fontsize(p, 12.5, int(card_w*1.15)))
            py -= 7.2
    for i in range(n-1):
        x0 = margin + i*(card_w+gap) + card_w
        x1 = margin + (i+1)*(card_w+gap)
        ax.add_patch(FancyArrowPatch((x0+0.3, card_y+card_h/2), (x1-0.3, card_y+card_h/2), arrowstyle="-|>", mutation_scale=20, lw=2.3, color="#8A97A6"))
    if footer:
        ax.add_patch(FancyBboxPatch((3, 6), 94, 8, boxstyle="round,pad=0.5,rounding_size=2", fc="#E8EEF5", ec="#0065BD", lw=1.4))
        ax.text(50, 10, footer, ha="center", va="center", color="#0B3D63",
                fontsize=_fit_fontsize(footer, 14, 70), fontstyle="italic", fontweight="bold")
    fig.savefig(out_png, facecolor=BG)   # no bbox_inches='tight' -> dimensions stay exactly 1600x900
    plt.close(fig)
    return out_png

def png_to_data_uri(png_path):
    with open(png_path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
```

### Embed and place

- Build the notebook with `nbformat` (`from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell`) so every cell automatically gets a valid unique `id`.
- For each of the three chunks: call `make_infographic(...)`, then `png_to_data_uri(...)`, and append the resulting `![descriptive alt text](data:image/png;base64,...)` line to the END of that chunk's relevant Concept Cell A markdown source. Distribute the three images through the Learning Material in teaching order.
- Use descriptive alt text that names the visualized topic (not "image" or "infographic").
- Do not add image-only cells, do not change the required cell sequence, and do not use external, temporary, or local-path image links.
- Base64 image data is allowed ONLY inside these three `data:image/png;base64,...` Markdown references; forbidden everywhere else.
- Delete the temporary PNG files after their data has been embedded.

### Validation (must pass before release)

Reopen the saved `.ipynb`, run `nbformat.validate()`, and confirm: exactly three Markdown cells each contain exactly one `data:image/png;base64,...` reference, every payload decodes to a valid non-empty PNG of the intended size, every cell has a unique `id`, and each image sits in the correct Concept Cell A in teaching order. Visually verify each rendered image's labels against the lesson content.
