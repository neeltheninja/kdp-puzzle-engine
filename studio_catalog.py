"""Reusable presets and topic packs derived from the project's real word lists."""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import cover

ROOT = Path(__file__).resolve().parent
LAYOUTS = ['framed', 'minimal', 'poster', 'split', 'band', 'gallery']
PATTERNS = ['plain', 'botanical', 'geometric', 'waves']
DEFAULT_DESIGN = {'bg': '#f4efe2', 'ink': '#203a26', 'accent': '#6b8e6b', 'highlight': '#ffd354',
                  'font': 'sans', 'layout': 'framed', 'pattern': 'botanical', 'margin': 54,
                  'font_size': 18, 'grid_size': 15, 'word_columns': 3, 'solution_density': 4,
                  'gridlines': True, 'reverse': True, 'diagonal': True, 'color_interior': False,
                  'include_solutions': True, 'include_intro': True, 'page_numbers': True,
                  'title_align': 'center', 'image': '', 'image_x': 50, 'image_y': 50,
                  'image_zoom': 100, 'image_opacity': 100, 'dedication': '', 'instructions': ''}


def presets():
    return [{'id': f'{name}-{layout}-{pattern}', 'name': f'{name.replace("-", " ").title()} · {layout.title()} · {pattern.title()}',
             'design': {**DEFAULT_DESIGN, 'layout': layout, 'pattern': pattern,
                        **{key: '#%02x%02x%02x' % palette[source] for key, source in [('bg','bg'),('ink','deep'),('accent','accent'),('highlight','hi')]}}}
            for name, palette in cover.PALETTES.items() for layout in LAYOUTS for pattern in PATTERNS]


@lru_cache(maxsize=1)
def topics():
    result = {}
    seen = set()
    for path in sorted((ROOT / 'themes').glob('*.json')):
        try:
            book = json.loads(path.read_text(encoding='utf-8'))
            for puzzle in book['puzzles']:
                name = puzzle['name'].strip()
                if name.lower() in seen:
                    continue
                seen.add(name.lower())
                key = hashlib.sha256(name.lower().encode()).hexdigest()[:16]
                result[key] = {'id': key, 'name': name, 'category': path.stem.replace('-', ' ').title(),
                               'palette': book.get('palette', 'nature'), 'puzzle': puzzle}
        except (ValueError, KeyError, TypeError):
            continue
    return result


TRENDS = [
    {'name': 'Logic & little mysteries', 'date': '2026-10-30', 'market': 'Canada',
     'note': 'BookNet reports continued growth in logic and brain-teaser sales. This is category evidence, not a forecast for an individual title.',
     'idea': 'An original library mystery atmosphere: ink blue, clues, maps, and numbered chapters. Use Sudoku or mazes; the engine does not generate narrative deduction puzzles.',
     'url': 'https://booknetcanada.ca/blog/2026/10/30/tracking-pre-holiday-subject-trends/'},
    {'name': 'Cozy, handmade worlds', 'date': '2025-12-15', 'market': 'US retail forecast for 2026',
     'note': 'Penguin Random House highlights cozy products, crafts, nostalgia, and tactile activities in its 2026 retail forecast.',
     'idea': 'Knitting baskets, cottage kitchens, birdwatching, warm paper, and original botanical illustrations.',
     'url': 'https://www.penguinrandomhouseretail.com/2025/12/15/trendspotting-your-prh-retail-2026-forecast/'},
    {'name': 'Screen-free rituals', 'date': '2026 Q1 data', 'market': 'US print books',
     'note': 'Circana identifies growth in hands-on categories including puzzles, coloring, guided journals, and needlework.',
     'idea': 'Morning coffee word searches, family travel mazes, and gentle daily puzzle routines with spacious typography.',
     'url': 'https://www.circana.com/post/turning-the-page-on-2026-book-trends'},
    {'name': 'A seasonal gift, with specifics', 'date': '2026 spring/summer catalogue', 'market': 'Publisher catalogue',
     'note': 'Dover’s catalogue features botanical activity books, bird subjects, and cozy Christmas coloring. Catalogue presence is inspiration, not proof of sales.',
     'idea': 'Original winter woodland artwork, garden birds, kitchen traditions, and seasonal word collections.',
     'url': 'https://www.doverpublications.com/retailers/pdfs/DoverNewTitlesSpringSummer2026.pdf'},
]
