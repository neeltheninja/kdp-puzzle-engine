# KDP Puzzle Engine

[![Live Demo](https://img.shields.io/badge/Live_Demo-GitHub_Pages-brightgreen)](https://neeltheninja.github.io/kdp-puzzle-engine/)
![Python](https://img.shields.io/badge/python-3.11-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> 🚀 **Live Studio Web App**: [https://neeltheninja.github.io/kdp-puzzle-engine/](https://neeltheninja.github.io/kdp-puzzle-engine/)

Generates print-ready, large-print puzzle books — word search, Sudoku, and mazes — as camera-ready PDFs for Amazon KDP. Swap in a themed word list and it produces a complete new book: interior PDF, cover, and back-cover wrap, laid out to KDP's print specs.

The premise: most puzzle-book sellers on KDP build books by hand, one at a time. This generates them, so a new niche is a new JSON file away from a new title rather than a new manual layout job.

## Sample output

<table><tr>
<td><img src="docs/sample-wordsearch-cover.png" width="280" alt="Sample word search book cover"><br><sub>wordsearch.py + cover.py</sub></td>
<td><img src="docs/sample-sudoku-cover.png" width="280" alt="Sample Sudoku book cover"><br><sub>sudoku.py + cover_sudoku.py</sub></td>
</tr></table>

## Generators

- **`wordsearch.py`** — takes a theme JSON (a name + word list), lays out a large-print grid guaranteed to place every word, and renders front matter, puzzles, and a full solutions section to an 8.5x11 interior PDF.
- **`sudoku.py`** — standard 9x9 puzzles. Generates valid solved grids via symmetry-preserving transformations of a base grid, then removes cells to hit a target difficulty.
- **`mazes.py`** — perfect mazes (exactly one solution path) via recursive backtracking, one per page, solutions at the back.
- **`cover.py`** / **`cover_sudoku.py`** / **`cover_maze.py`** / **`wrap_cover.py`** — cover and full-wrap (front + spine + back) generation at 300 DPI, palette-matched per theme.

## Automation layer

- **`build_theme_book.py`** — the end-to-end path for a themed word-search book: theme JSON in, complete `{interior.pdf, cover.png, wrap.pdf}` folder out.
- **`auto_factory.py`** — an unattended factory mode that rotates across a fixed set of recipes (Sudoku/Mazes at a few difficulty tiers) so scheduled runs produce genuinely different books back-to-back rather than near-duplicates (which KDP penalizes), tracking its own position in the rotation between runs.
- **`gen_themes.py`** — drafts a theme's word list via a local LLM (Ollama) as a starting point — output is intentionally treated as a first draft, not a final list.
- **`preflight.py`** — a compliance check that runs on a built book folder before it's ever uploaded: page-size/count sanity, and the specific formatting issues that have triggered Amazon KDP review flags in practice (e.g. author-field/imprint conflicts, spine text sitting too close to the trim edge on thin books).
- **`publish_tools/`** — small scripts that drive already-published KDP listings: updating a book's search keywords, attaching a book to a series, and the underlying CDP session handling they share.

## Themes

`themes/*.json` are the word lists that drive `wordsearch.py` — one file per niche (animals, nature, travel, holidays, and so on). `specs/*.json` are lighter skeleton specs (just sub-theme names) used as input to `gen_themes.py` when drafting a new one.

## Stack

Python, reportlab (PDF generation), Pillow (cover rendering), a local Ollama model for word-list drafting, Chrome DevTools Protocol for the KDP listing-management tools.

## Running it

### Puzzle Studio (GUI)

```sh
python -m pip install -r requirements.txt
python studio.py
```

The browser opens automatically. Keep the terminal running while you work.
Python 3.11+ is required. Windows, macOS, and Linux use the same commands
(use `python3` if that is your Python command).

- Create word-search, Sudoku, and maze books with puzzle and solution previews.
- Customize titles, authors, difficulty, count, seeds, cover palettes, badges,
  back-cover copy, and cross-promotions. Draft settings are saved in your browser.
- Browse, edit, import, and export themes; draft new word lists with local Ollama.
- Build in the background, cancel jobs, inspect logs, and resume browsing after
  a server restart. Interrupted jobs are marked for restarting.
- Browse generated books, view PDFs, rerun preflight, rebuild covers as a new
  edition, reuse project settings, and download individual files or a ZIP.
- Run the saved six-recipe factory rotation and access the existing Chrome/CDP
  tools for keyword updates and series attachment.

The interface uses plain HTML, CSS, and JavaScript: no Node installation, build
step, CDN, or extra Python dependencies. Fonts fall back to ReportLab's bundled
fonts when system fonts are unavailable. Cover concepts are approximate;
downloaded PDFs and cover images are the final output. Preflight uses the
project's existing checks and does not guarantee KDP acceptance.

To use a phone, tablet, or another computer on your local network:

```sh
python studio.py --host 0.0.0.0 --no-browser
```

Open the printed access link on the other device, replacing `127.0.0.1` with
the engine computer's LAN IP. Preserve the `#token=...` part. The access token
is private and changes when the server restarts. Allow the chosen port through
your firewall if needed. Use `--port 9000` to change the default `8765`.
The local server is intended for a trusted LAN, not direct public Internet
hosting; use an authenticated HTTPS reverse proxy for remote deployment.

Ollama drafting requires a running local Ollama service and the selected model
(default `qwen2.5:3b`). Publishing tools require Chrome on the engine computer,
remote debugging on port 9222 with a separate profile, and a signed-in KDP tab.
The UI requires an explicit action before changing a live listing. Series
attachment retains the existing script's fixed-series behavior, described in
the interface. KDP UI changes may require updating these scripts.

### Command line

```
pip install -r requirements.txt
python3 wordsearch.py --themes themes/nature.json --out out/nature.pdf
python3 build_theme_book.py --theme themes/beach-vacation.json  # full book folder: interior + cover + wrap
python3 auto_factory.py                                     # one factory-mode book, next recipe in rotation
python3 preflight.py out/beach-vacation/                    # compliance check before upload
```

### Design desk, topic packs, and AI workshop

The **Design & artwork** page includes 336 visual presets (14 palettes × six
layouts × four decorative motifs). These are reusable design combinations,
not 336 independently researched niches. Change paper/ink/accent/highlight
colors, drag swatches between roles, choose fonts and alignment, and upload
PNG/JPEG/WebP artwork. Uploaded images supply draggable color swatches and
support crop position, zoom, and opacity. Original botanical, wave, and
geometric artwork can be rendered without uploads. Save styles in your browser
or export/import style JSON; artwork files must remain on the engine computer.

Interior controls affect the actual PDF: margins, maximum type size, word-list
columns, 10–22-cell word-search grids, diagonal/reverse placement, gridlines,
monochrome/color ink, dedication, custom instructions, page numbers, and 1/4/6
solutions per page. The print trim remains 8.5 × 11 inches. Type automatically
shrinks to fit a grid; turn off solutions or intro pages only when intentional.
Color interiors target standard color on white paper, using the same spine
factor as black ink on white paper in [KDP’s cover guide](https://kdp.amazon.com/en_US/help/topic/G201953020).
Premium color is not supported by this setting. Verify page-count eligibility
and final dimensions using the KDP cover calculator. A concept preview is not a print proof.

**Theme collection → Browse topic packs** exposes the 1,096 distinct named
subthemes in the bundled word lists. Each pack is one puzzle; select several
and combine them into a book, then edit and save it. These reuse the supplied
vocabulary, not newly researched word lists. Newly saved themes are added to
the topic index after a server restart.

**AI workshop** supports:

| Provider | API base | Environment key |
| --- | --- | --- |
| OpenRouter | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |
| Token Harbor | `https://tokenharbor.ai/v1` | `TOKENHARBOR_API_KEY` |
| Together AI | `https://api.together.ai/v1` | `TOGETHER_API_KEY` |
| DeepSeek | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` |
| Local Ollama | `http://127.0.0.1:11434/v1` | none |
| Custom compatible API | enter the base URL | `STUDIO_LLM_API_KEY` |

Enter a key in the password field or set the matching environment variable.
Keys are retained only in server memory, never in browser storage, job files,
style exports, or books. **Forget session key** removes the in-memory key;
unset an environment key and restart to remove that alternative. Custom remote
endpoints require HTTPS; loopback HTTP is allowed. API redirects are refused
to avoid forwarding credentials to a different endpoint.

Load the current model catalogue or enter an exact model ID. Theme generation
produces up to 24 puzzles per request, a palette/design proposal, and an artwork
prompt. Invalid JSON, incorrect counts, duplicate words, and unsupported style
values are rejected before saving. Optional JSON mode needs model support.
Generated drafts still need editorial review. Generation can cost money; the
client never automatically retries a paid request. Cancellation discards an
in-flight response when it returns; it cannot undo provider charges.

Artwork generation uses OpenRouter's documented `POST /api/v1/images`, with
models discovered from `GET /api/v1/images/models`. Other connected providers
currently generate theme text only. PNG, JPEG, and WebP responses are accepted;
vector-only responses are not. No live paid requests were made during this
implementation. Provider/model compatibility still needs verification with
your account. AI provenance is retained in theme and artwork metadata and noted
in generated listing files.

The **Trend notebook** is dated research checked on **2026-11-14**, not a live
sales-ranking feed. It links to the following sources and distinguishes market
evidence from suggested designs:

- [BookNet Canada: pre-holiday subject trends](https://booknetcanada.ca/blog/2026/10/30/tracking-pre-holiday-subject-trends/)
- [Penguin Random House: 2026 retail forecast](https://www.penguinrandomhouseretail.com/2025/12/15/trendspotting-your-prh-retail-2026-forecast/)
- [Circana: 2026 book trends](https://www.circana.com/post/turning-the-page-on-2026-book-trends)
- [Dover: spring/summer 2026 catalogue](https://www.doverpublications.com/retailers/pdfs/DoverNewTitlesSpringSummer2026.pdf)

Integration references: [OpenRouter images](https://openrouter.ai/docs/guides/overview/multimodal/image-generation),
[Token Harbor chat](https://tokenharbor.ai/docs/api/curl),
[Token Harbor models](https://tokenharbor.ai/docs/api/models),
[Together compatibility](https://docs.together.ai/docs/inference/openai-compatibility),
[DeepSeek API](https://api-docs.deepseek.com/).
