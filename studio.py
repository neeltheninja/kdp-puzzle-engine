#!/usr/bin/env python3
"""Cross-platform Puzzle Studio. Run: python studio.py"""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import mimetypes
import os
from pathlib import Path
import random
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, quote, unquote, urlsplit
import urllib.request
import uuid
import webbrowser
import zipfile

from PIL import Image
from pypdf import PdfReader
import auto_factory
import cover
import gen_themes
import mazes
import preflight
import sudoku
import wordsearch
import studio_ai
import studio_catalog
import book_design

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'out'
STATE = OUT / '.studio'
TOKEN = secrets.token_urlsafe(32)
JOBS = {}
LOCK = threading.RLock()
PREVIEW_LOCK = threading.Lock()
# One build at a time keeps 300-DPI rendering memory bounded and factory rotation ordered.
WORKER = ThreadPoolExecutor(max_workers=1)
FILE_TYPES = {'.pdf', '.png', '.json', '.md', '.txt', '.csv'}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def beneath(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError('Invalid path.')
    return path


def integer(value, low, high, name):
    if isinstance(value, bool) or not re.fullmatch(r'-?\d+', str(value)):
        raise ValueError(f'{name} must be a whole number.')
    value = int(value)
    if not low <= value <= high:
        raise ValueError(f'{name} must be between {low} and {high}.')
    return value


def text(value, name, maximum=200, required=True):
    if not isinstance(value, str) or len(value) > maximum or '\x00' in value:
        raise ValueError(f'{name} must be text, up to {maximum} characters.')
    value = value.strip()
    if required and not value:
        raise ValueError(f'{name} is required.')
    return value


def theme_data(data):
    if not isinstance(data, dict):
        raise ValueError('Theme must be a JSON object.')
    data = dict(data)
    data['title'] = text(data.get('title'), 'Title', 100)
    data['subtitle'] = text(data.get('subtitle', ''), 'Subtitle', 200, False)
    data['author'] = text(data.get('author', ''), 'Author', 80, False)
    puzzles = data.get('puzzles')
    if not isinstance(puzzles, list) or not 1 <= len(puzzles) <= 300:
        raise ValueError('A theme needs 1–300 puzzles.')
    for puzzle in puzzles:
        if not isinstance(puzzle, dict):
            raise ValueError('Each puzzle needs a name and words.')
        puzzle['name'] = text(puzzle.get('name'), 'Puzzle name', 80)
        words = puzzle.get('words')
        if not isinstance(words, list) or not 1 <= len(words) <= 30:
            raise ValueError(f'{puzzle["name"]}: use 1–30 words.')
        if any(not isinstance(w, str) or not re.fullmatch(r'[a-zA-Z]{1,15}', w) for w in words):
            raise ValueError(f'{puzzle["name"]}: words must contain 1–15 English letters, without spaces.')
        puzzle['words'] = list(dict.fromkeys(w.upper() for w in words))
    also = data.get('also_from', [])
    if not isinstance(also, list) or any(not isinstance(x, dict) for x in also):
        raise ValueError('also_from must be a list of book objects.')
    return data


def settings(data):
    kind = data.get('kind', 'wordsearch')
    if kind not in ('wordsearch', 'sudoku', 'maze'):
        raise ValueError('Unknown puzzle type.')
    result = {k: v for k, v in data.items() if k in ('title','subtitle','author','count','seed','profile','palette','badge','back','also_from','theme','theme_data','keywords')}
    result['kind'] = kind
    if data.get('design') is not None:
        result['design'] = book_design.validate(data['design'])
    result['title'] = text(data.get('title'), 'Title', 100)
    result['subtitle'] = text(data.get('subtitle', ''), 'Subtitle', 200, False)
    result['author'] = text(data.get('author'), 'Author', 80)
    if 'evergreen puzzle press' in result['author'].lower():
        raise ValueError('Use a person or pen name in the author field; the imprint belongs on the back cover.')
    result['seed'] = integer(data.get('seed', 7), 0, 2147483647, 'Seed')
    result['count'] = integer(data.get('count', 48), 1, 300, 'Puzzle count')
    result['profile'] = data.get('profile', 'mixed')
    if result['profile'] not in ('easy', 'mixed', 'hard'):
        raise ValueError('Choose easy, mixed, or hard difficulty.')
    result['palette'] = data.get('palette', 'nature')
    if result['palette'] not in cover.PALETTES:
        raise ValueError('Choose an available cover palette.')
    result['badge'] = text(data.get('badge', ''), 'Badge', 42, False)
    result['back'] = text(data.get('back', ''), 'Back-cover text', 1500, False)
    also = data.get('also_from', [])
    if not isinstance(also, list) or len(also) > 7 or any(not isinstance(book, dict) for book in also):
        raise ValueError('Also-from books must be a list of up to seven book objects.')
    for book in also:
        text(book.get('title'), 'Also-from title', 100)
        text(book.get('subtitle', ''), 'Also-from subtitle', 200, False)
    if kind == 'wordsearch':
        result['theme_data'] = theme_data(data['theme_data']) if data.get('theme_data') else theme_data(read_json(beneath(ROOT / 'themes', data.get('theme', 'nature.json'))))
        grid_size = result.get('design', {}).get('grid_size', 15)
        if any(len(word) > grid_size for puzzle in result['theme_data']['puzzles'][:result['count']] for word in puzzle['words']):
            raise ValueError('Some words are longer than the selected grid. Increase the grid size.')
        if result['count'] > len(result['theme_data']['puzzles']):
            raise ValueError('Puzzle count cannot exceed the number of puzzles in the theme.')
    return result


def update(job, **changes):
    with LOCK:
        job.update(changes)
        write_json(STATE / (job['id'] + '.json'), job)


def run_script(job, script, *args, env=None):
    log = STATE / (job['id'] + '.log')
    with log.open('a', encoding='utf-8') as output:
        process = subprocess.Popen([sys.executable, '-u', str(ROOT / script), *map(str, args)],
                                   cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                   env={**os.environ, 'PYTHONIOENCODING': 'utf-8', **(env or {})})
        deadline = time.monotonic() + 3600
        while process.poll() is None:
            if job.get('cancel') or time.monotonic() > deadline:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise RuntimeError('Cancelled.' if job.get('cancel') else 'Operation timed out.')
            time.sleep(.2)
    if process.returncode:
        message = log.read_text(encoding='utf-8', errors='replace')[-2500:]
        raise RuntimeError(message or f'{script} failed.')


def check_book(folder):
    try:
        ok, lines = preflight.preflight(str(folder))
        return {'ok': ok, 'checks': lines}
    except Exception as error:
        return {'ok': False, 'checks': [f'FAIL {error}']}


def book_files(folder):
    return [{'name': p.name, 'size': p.stat().st_size,
             'url': '/files/' + quote(p.relative_to(OUT).as_posix(), safe='/')}
            for p in sorted(folder.iterdir()) if p.is_file() and p.suffix in FILE_TYPES and not p.name.startswith('.')]


def build(job, config, folder=None, covers_only=False):
    slug = re.sub(r'[^a-z0-9]+', '-', config['title'].lower()).strip('-')[:60] or 'book'
    folder = folder or OUT / f'{slug}-{job["id"][:8]}'
    folder.mkdir(parents=True, exist_ok=True)
    update(job, book=folder.relative_to(OUT).as_posix())
    if not covers_only:
        write_json(folder / 'project.json', config)
        update(job, progress=10, stage='Generating puzzles and solutions')
        args = ['--out', folder / 'interior.pdf', '--seed', config['seed'], '--title', config['title'], '--subtitle', config['subtitle'], '--author', config['author']]
        if config.get('design'):
            if config['kind'] == 'wordsearch':
                write_json(folder / 'theme.json', {**config['theme_data'], 'puzzles': config['theme_data']['puzzles'][:config['count']]})
            if config['design']['image']:
                shutil.copy2(OUT / 'assets' / config['design']['image'], folder / 'artwork.png')
            run_script(job, 'book_design.py', '--project', folder / 'project.json', '--out', folder / 'interior.pdf')
        elif config['kind'] == 'wordsearch':
            theme = {**config['theme_data'], 'puzzles': config['theme_data']['puzzles'][:config['count']]}
            write_json(folder / 'theme.json', theme)
            run_script(job, 'wordsearch.py', '--themes', folder / 'theme.json', *args)
        else:
            also = config.get('also_from', [])
            if also:
                write_json(folder / 'also_from.json', also)
                args.extend(['--also-from', folder / 'also_from.json'])
            run_script(job, 'sudoku.py' if config['kind'] == 'sudoku' else 'mazes.py', '--count', config['count'], '--profile', config['profile'], *args)
    pages = len(PdfReader(folder / 'interior.pdf').pages)
    update(job, progress=60, stage='Rendering the 300 DPI cover')
    args = ['--title', config['title'], '--subtitle', config['subtitle'], '--author', config['author'], '--badge', config['badge'] or f'{config["count"]} LARGE PRINT PUZZLES', '--out', folder / 'cover.png']
    script = {'wordsearch': 'cover.py', 'sudoku': 'cover_sudoku.py', 'maze': 'cover_maze.py'}[config['kind']]
    if config['kind'] == 'wordsearch':
        args.extend(['--palette', config['palette']])
    if config.get('design'):
        run_script(job, 'book_design.py', '--project', folder / 'project.json', '--out', folder / 'cover.png', '--cover')
    else:
        run_script(job, script, *args)
    with Image.open(folder / 'cover.png') as thumbnail:
        thumbnail.thumbnail((510, 660))
        thumbnail.save(folder / 'thumbnail.png')
    update(job, progress=80, stage='Creating the full-wrap PDF')
    palette = config['palette'] if config['kind'] == 'wordsearch' else config['kind']
    back = config['back'] or f"Enjoy {config['count']} large print {config['kind'].replace('wordsearch', 'word search')} puzzles.\n\nOne puzzle per page, generous spacing, and complete solutions at the back.\n\nTake a little time for yourself, one puzzle at a time."
    if config.get('design', {}).get('include_solutions') is False and not config['back']:
        back = back.replace('and complete solutions at the back', 'and room to solve at your own pace')
    run_script(job, 'wrap_cover.py', '--front', folder / 'cover.png', '--pages', pages, '--palette', palette, '--title', config['title'], '--author', config['author'], '--back', back, '--out', folder / 'wrap.pdf', *(['--design', folder / 'project.json'] if config.get('design') else []))
    listing = f"# {config['title']}\n\nAuthor: {config['author']}\n\n{config['subtitle']}\n\n{pages} pages · 8.5 × 11 inches · black and white on white paper\n\n## Description\n\n{back}\n\n## Keywords\n\n" + '\n'.join(config.get('keywords', [])) + '\n\nReview the files, metadata, content disclosures, and current KDP requirements before publishing.\n'
    if config.get('design', {}).get('color_interior'):
        listing = listing.replace('black and white on white paper', 'STANDARD COLOR interior on white paper; verify page-count eligibility and the selected print option')
    if config.get('theme_data', {}).get('ai_generated'):
        listing += '\nTheme vocabulary was AI-generated. Review content and applicable KDP AI disclosure settings.\n'
    if config.get('design', {}).get('image'):
        meta = OUT / 'assets' / (config['design']['image'] + '.json')
        if meta.exists() and read_json(meta).get('ai_generated'):
            listing += '\nCover artwork was AI-generated. Review artwork and applicable KDP AI disclosure settings.\n'
    (folder / 'LISTING.md').write_text(listing, encoding='utf-8')
    update(job, progress=95, stage='Checking the finished files')
    report = check_book(folder)
    write_json(folder / 'preflight.json', report)
    return {'book': folder.relative_to(OUT).as_posix(), 'pages': pages, 'report': report}


def execute(job, data):
    try:
        if job.get('cancel'):
            raise RuntimeError('Cancelled.')
        update(job, status='running', stage='Starting', progress=3)
        action = job['action']
        if action == 'build':
            result = build(job, data)
        elif action == 'covers':
            source = beneath(OUT, data['book'])
            config = settings(read_json(source / 'project.json'))
            destination = OUT / f'{source.name}-cover-{job["id"][:8]}'
            destination.mkdir()
            for filename in ('interior.pdf', 'project.json', 'theme.json', 'artwork.png'):
                if (source / filename).is_file():
                    shutil.copy2(source / filename, destination / filename)
            result = build(job, config, destination, covers_only=True)
        elif action == 'factory':
            index_file = OUT / 'auto' / '.run_index'
            index = int(index_file.read_text()) if index_file.exists() else 0
            recipe = dict(auto_factory.RECIPES[index % len(auto_factory.RECIPES)])
            volume = index // len(auto_factory.RECIPES) + 1
            recipe.update(author=auto_factory.AUTHOR, seed=20260609 + index * 7, palette='nature', back='')
            recipe['title'] += f' · Volume {volume}' if volume > 1 else ''
            folder = OUT / 'auto' / f'{index + 1:04d}_{recipe["slug"]}_v{volume}'
            if folder.exists():
                raise ValueError('The next factory folder already exists. Resolve the existing run before advancing the rotation.')
            result = build(job, settings(recipe), folder)
            index_file.write_text(str(index + 1))
        elif action == 'preflight':
            folder = beneath(OUT, data['book'])
            result = check_book(folder)
            write_json(folder / 'preflight.json', result)
        elif action in ('ai-theme', 'ai-image'):
            connection = data['connection']
            update(job, stage='Waiting for the selected AI provider', progress=15)
            if action == 'ai-theme':
                raw = studio_ai.draft(connection, data['brief'], data['puzzles'], data['words'], data['model'])
                generated = theme_data(raw)
                if generated.get('design'):
                    generated['design'] = book_design.validate(generated['design'])
                if any(len(p['words']) != data['words'] for p in generated['puzzles']):
                    raise ValueError('The model repeated words. Try a more specific brief.')
                if job.get('cancel'):
                    raise RuntimeError('Cancelled.')
                name = 'ai-' + job['id'][:8] + '.json'
                write_json(ROOT / 'themes' / name, generated)
                result = {'theme': name, 'message': 'AI draft saved. Review vocabulary and artwork instructions before building.'}
            else:
                image_bytes = studio_ai.image(connection, data['brief'], data['model'])
                if job.get('cancel'):
                    raise RuntimeError('Cancelled.')
                result = {'asset': save_asset(image_bytes, ai_generated=True), 'message': 'Artwork saved to your image shelf.'}
        elif action == 'draft':
            spec = {'title': data['title'], 'subtitle': '', 'author': 'E. P. Greenwood', 'palette': 'nature', 'themes': data['topics']}
            spec_path = STATE / (job['id'] + '-spec.json')
            write_json(spec_path, spec)
            target = ROOT / 'themes' / ('draft-' + job['id'][:8] + '.json')
            update(job, stage='Drafting words with local Ollama', progress=15)
            run_script(job, 'gen_themes.py', '--spec', spec_path, '--out', target, env={'OLLAMA_MODEL': data['model']})
            result = {'theme': target.name, 'message': 'Draft saved. Review the words in the theme editor before building.'}
        elif action == 'publish':
            update(job, stage='Updating the KDP listing in Chrome', progress=20)
            script = 'kw_update.py' if data['operation'] == 'keywords' else 'series_attach.py'
            run_script(job, 'publish_tools/' + script, data['book_id'], *data.get('keywords', []))
            log = (STATE / (job['id'] + '.log')).read_text(encoding='utf-8')
            result = json.loads(log.strip().splitlines()[-1])
            if result.get('result') not in ('published', 'attached', 'already-in-series'):
                raise RuntimeError('KDP did not confirm completion: ' + json.dumps(result))
        else:
            raise ValueError('Unknown operation.')
        update(job, status='completed', progress=100, stage='Complete', result=result)
    except Exception as error:
        update(job, status='cancelled' if job.get('cancel') else 'failed', stage=str(error), error=str(error))


def submit(data):
    action = data.get('action')
    if action == 'build':
        data = settings(data)
    elif action in ('preflight', 'covers'):
        folder = beneath(OUT, text(data.get('book'), 'Book folder'))
        if not folder.is_dir() or STATE in folder.parents:
            raise ValueError('Book folder not found.')
    elif action in ('ai-theme', 'ai-image'):
        data['brief'] = text(data.get('brief'), 'Creative brief', 6000)
        data['model'] = text(data.get('model'), 'Model ID', 160)
        data['connection'] = studio_ai.connection({'provider': data.get('provider'), 'json_mode': data.get('json_mode') is True})
        data['title'] = 'AI theme' if action == 'ai-theme' else 'AI artwork'
        if action == 'ai-theme':
            data['puzzles'] = integer(data.get('puzzles', 12), 1, 24, 'AI puzzle count')
            data['words'] = integer(data.get('words', 14), 6, 24, 'Words per puzzle')
        elif data['connection']['provider'] != 'openrouter':
            raise ValueError('Select OpenRouter for artwork generation.')
    elif action == 'draft':
        data['title'] = text(data.get('title'), 'Title', 100)
        data['model'] = text(data.get('model'), 'Ollama model', 100)
        topics = data.get('topics')
        if not isinstance(topics, list) or not 1 <= len(topics) <= 100:
            raise ValueError('Provide 1–100 topics.')
        data['topics'] = [text(x, 'Topic', 80) for x in topics]
    elif action == 'publish':
        if data.get('confirmed') is not True:
            raise ValueError('Confirm the listing change first.')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', str(data.get('book_id', ''))):
            raise ValueError('Enter a valid KDP book ID.')
        if data.get('operation') not in ('keywords', 'series'):
            raise ValueError('Unknown listing operation.')
        if data['operation'] == 'keywords':
            keywords = data.get('keywords')
            if not isinstance(keywords, list) or len(keywords) != 7:
                raise ValueError('Provide exactly seven keywords.')
            data['keywords'] = [text(k, 'Keyword', 50) for k in keywords]
        else:
            data.pop('keywords', None)
    elif action != 'factory':
        raise ValueError('Unknown operation.')
    with LOCK:
        if sum(j['status'] in ('queued', 'running') for j in JOBS.values()) >= 12:
            raise ValueError('The queue is full. Wait for a job to finish.')
        job = {'id': uuid.uuid4().hex, 'action': action, 'title': data.get('title', action.title()),
               'status': 'queued', 'stage': 'Queued', 'progress': 0, 'created': datetime.now(timezone.utc).isoformat()}
        JOBS[job['id']] = job
        update(job)
        WORKER.submit(execute, job, data)
        return dict(job)


def preview(data):
    kind = data.get('kind', 'wordsearch')
    seed = integer(data.get('seed', 7), 0, 2147483647, 'Seed')
    rng = random.Random(seed)
    if kind == 'wordsearch':
        theme = theme_data(data['theme_data']) if data.get('theme_data') else theme_data(read_json(beneath(ROOT / 'themes', data.get('theme', 'nature.json'))))
        index = integer(data.get('index', 0), 0, len(theme['puzzles']) - 1, 'Puzzle index')
        puzzle = theme['puzzles'][index]
        design = book_design.validate(data.get('design', {}))
        with PREVIEW_LOCK:
            old_directions = wordsearch.DIRS
            book_design.setup_words(design)
            state = random.getstate()
            try:
                random.seed(seed)
                for previous in theme['puzzles'][:index]:
                    wordsearch.generate_puzzle(wordsearch.clean_words(previous['words']), design['grid_size'])
                grid, paths, words = wordsearch.generate_puzzle(wordsearch.clean_words(puzzle['words']), design['grid_size'])
            finally:
                random.setstate(state)
                wordsearch.DIRS = old_directions
        return {'kind': kind, 'name': puzzle['name'], 'grid': grid, 'paths': paths, 'words': words}
    profile = data.get('profile', 'mixed')
    difficulty = {'mixed': 'medium', 'easy': 'easy', 'hard': 'hard'}.get(profile)
    if not difficulty:
        raise ValueError('Invalid difficulty.')
    if kind == 'sudoku':
        solved = sudoku.make_solved(rng)
        return {'kind': kind, 'name': 'Sudoku', 'grid': sudoku.make_puzzle(solved, difficulty, rng), 'solution': solved}
    if kind == 'maze':
        n = {'easy': 11, 'medium': 15, 'hard': 19}[difficulty]
        walls = mazes.gen_maze(n, n, rng)
        return {'kind': kind, 'name': 'Maze', 'size': n, 'walls': [[x, y, sorted(w)] for (x, y), w in walls.items()], 'path': mazes.solve(walls, n, n)}
    raise ValueError('Unknown puzzle type.')


def library():
    books = []
    for pdf in OUT.rglob('interior.pdf'):
        if STATE in pdf.parents:
            continue
        folder = pdf.parent
        try:
            config = read_json(folder / 'project.json') if (folder / 'project.json').exists() else {}
            report = read_json(folder / 'preflight.json') if (folder / 'preflight.json').exists() else None
            books.append({'id': folder.relative_to(OUT).as_posix(), 'title': config.get('title', folder.name.replace('-', ' ')),
                          'kind': config.get('kind', 'book'), 'modified': pdf.stat().st_mtime, 'report': report,
                          'editable': bool(config), 'files': book_files(folder)})
        except (OSError, ValueError):
            continue
    return sorted(books, key=lambda book: book['modified'], reverse=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def authenticated(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
        except Exception:
            return False
        bearer = self.headers.get('Authorization', '').removeprefix('Bearer ')
        session = cookie.get('studio_session')
        return secrets.compare_digest(bearer, TOKEN) or bool(session and secrets.compare_digest(session.value, TOKEN))

    def send(self, data, status=200, mime='application/json', headers=None):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; script-src 'self'; connect-src 'self'; frame-src 'self'; frame-ancestors 'none'")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            url = urlsplit(self.path)
            path = unquote(url.path)
            if path in ('/', '/app.js', '/style.css', '/customize.js', '/customize.css'):
                file = ROOT / 'web' / ('index.html' if path == '/' else path[1:])
                return self.send(file.read_bytes(), mime=mimetypes.guess_type(file.name)[0] or 'text/plain')
            if not self.authenticated():
                return self.send({'error': 'Open the access link printed by studio.py to connect.'}, 401)
            if path == '/api/bootstrap':
                themes = []
                for file in sorted((ROOT / 'themes').glob('*.json')):
                    try:
                        data = read_json(file)
                        themes.append({'id': file.name, 'title': data.get('title', file.stem), 'count': len(data.get('puzzles', [])), 'palette': data.get('palette', 'nature')})
                    except (OSError, ValueError):
                        continue
                index_file = OUT / 'auto' / '.run_index'
                index = int(index_file.read_text()) if index_file.exists() else 0
                return self.send({'themes': themes, 'palettes': cover.PALETTES, 'recipes': auto_factory.RECIPES, 'factory_index': index, 'model': gen_themes.MODEL, 'design': studio_catalog.DEFAULT_DESIGN, 'presets': studio_catalog.presets(), 'topic_count': len(studio_catalog.topics()), 'providers': studio_ai.PROVIDERS, 'trends': studio_catalog.TRENDS, 'trends_checked': '2026-11-14'}, headers={'Set-Cookie': f'studio_session={TOKEN}; HttpOnly; SameSite=Strict; Path=/'})
            if path == '/api/topics':
                return self.send(list(studio_catalog.topics().values()))
            if path == '/api/assets':
                return self.send([{'id': p.name, 'url': '/files/assets/' + p.name} for p in sorted((OUT / 'assets').glob('*.png'))])
            if path == '/api/ai-status':
                return self.send({name: bool(studio_ai.CONNECTIONS.get(name, {}).get('key') or os.environ.get(p['env'])) for name, p in studio_ai.PROVIDERS.items()})
            if path == '/api/theme':
                name = parse_qs(url.query).get('id', ['nature.json'])[0]
                return self.send(read_json(beneath(ROOT / 'themes', name)))
            if path == '/api/books':
                return self.send(library())
            if path == '/api/jobs':
                with LOCK:
                    return self.send(list(JOBS.values())[-100:][::-1])
            if path == '/api/log':
                job_id = parse_qs(url.query).get('id', [''])[0]
                if job_id not in JOBS:
                    raise ValueError('Job not found.')
                log = STATE / (job_id + '.log')
                return self.send({'log': log.read_text(encoding='utf-8', errors='replace')[-20000:] if log.exists() else ''})
            if path == '/api/connections':
                result = {}
                for key, endpoint in [('ollama', 'http://127.0.0.1:11434/api/tags'), ('chrome', 'http://127.0.0.1:9222/json')]:
                    try:
                        with urllib.request.urlopen(endpoint, timeout=2) as response:
                            value = json.load(response)
                        result[key] = {'connected': True, 'models': [m['name'] for m in value.get('models', [])]} if key == 'ollama' else {'connected': any('kdp.amazon.com' in t.get('url', '') for t in value)}
                    except Exception:
                        result[key] = {'connected': False}
                return self.send(result)
            if path == '/api/download':
                folder = beneath(OUT, parse_qs(url.query).get('book', [''])[0])
                if not (folder / 'interior.pdf').exists() or STATE in folder.parents:
                    raise ValueError('Book not found.')
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
                    for file in book_files(folder):
                        archive.write(folder / file['name'], arcname=file['name'])
                return self.send(buffer.getvalue(), mime='application/zip', headers={'Content-Disposition': f'attachment; filename="{folder.name}.zip"'})
            if path.startswith('/files/'):
                file = beneath(OUT, path[7:])
                if STATE in file.parents or file.suffix not in FILE_TYPES or not file.is_file():
                    raise ValueError('File not found.')
                return self.send(file.read_bytes(), mime=mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
            self.send({'error': 'Not found.'}, 404)
        except (ValueError, OSError, KeyError, TypeError) as error:
            self.send({'error': str(error)}, 400)

    def do_POST(self):
        try:
            origin = self.headers.get('Origin')
            if origin and urlsplit(origin).netloc != self.headers.get('Host'):
                return self.send({'error': 'Cross-origin requests are not allowed.'}, 403)
            if not self.authenticated():
                return self.send({'error': 'Access link required.'}, 401)
            length = int(self.headers.get('Content-Length', 0))
            maximum = 14_000_000 if self.path == '/api/assets' else 2_000_000
            if not 0 < length <= maximum:
                raise ValueError('Request exceeds the upload limit.')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object.')
            path = urlsplit(self.path).path
            if path == '/api/design-validate':
                return self.send(book_design.validate(data.get('design')))
            if path == '/api/assets':
                try:
                    raw = base64.b64decode(data.get('data', '').split(',')[-1], validate=True)
                except ValueError:
                    raise ValueError('Invalid image data.') from None
                return self.send(save_asset(raw))
            if path == '/api/ai-connect':
                if data.get('forget'):
                    studio_ai.CONNECTIONS.pop(data.get('provider'), None)
                    return self.send({'ok': True})
                connection = studio_ai.connection(data)
                studio_ai.CONNECTIONS[connection['provider']] = {k: connection[k] for k in ('url','key')}
                return self.send({'ok': True})
            if path == '/api/ai-models':
                return self.send(studio_ai.models(studio_ai.connection(data), data.get('images') is True))
            if path == '/api/compose':
                ids = data.get('ids')
                if not isinstance(ids, list) or not 1 <= len(ids) <= 300 or any(not isinstance(i, str) or i not in studio_catalog.topics() for i in ids):
                    raise ValueError('Choose 1–300 topic packs.')
                selected = [studio_catalog.topics()[i] for i in dict.fromkeys(ids)]
                return self.send({'title': data.get('title') or 'My Word Search Collection', 'author': 'E. P. Greenwood', 'subtitle': '', 'palette': selected[0]['palette'], 'puzzles': [t['puzzle'] for t in selected]})
            if path == '/api/jobs':
                return self.send(submit(data), 202)
            if path == '/api/cancel':
                with LOCK:
                    job = JOBS.get(data.get('id'))
                    if not job or job['status'] not in ('queued', 'running'):
                        raise ValueError('No active job to cancel.')
                    update(job, cancel=True)
                return self.send({'ok': True})
            if path == '/api/preview':
                return self.send(preview(data))
            if path == '/api/themes':
                theme = theme_data(data.get('theme'))
                slug = re.sub(r'[^a-z0-9]+', '-', theme['title'].lower()).strip('-')[:60] or 'theme'
                name = f'{slug}-{uuid.uuid4().hex[:6]}.json'
                write_json(ROOT / 'themes' / name, theme)
                return self.send({'id': name})
            self.send({'error': 'Not found.'}, 404)
        except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
            self.send({'error': str(error)}, 400)


def save_asset(raw, ai_generated=False):
    if not raw or len(raw) > 10_000_000:
        raise ValueError('Upload an image smaller than 10 MB.')
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in ('PNG','JPEG','WEBP') or source.width * source.height > 20_000_000:
                raise ValueError('Use PNG, JPEG, or WebP artwork up to 20 megapixels.')
            from PIL import ImageOps
            normalized = ImageOps.exif_transpose(source).convert('RGBA')
            normalized.thumbnail((4000,4000))
    except (OSError, Image.DecompressionBombError):
        raise ValueError('This image could not be read safely.') from None
    name = uuid.uuid4().hex + '.png'
    folder = OUT / 'assets'; folder.mkdir(parents=True, exist_ok=True)
    normalized.save(folder / name, 'PNG')
    colors = normalized.convert('RGB').resize((100,100)).quantize(colors=6).convert('RGB').getcolors(10000)
    palette = ['#%02x%02x%02x' % color for _, color in sorted(colors, reverse=True)[:6]]
    meta = {'id': name, 'url': '/files/assets/' + name, 'width': normalized.width, 'height': normalized.height, 'colors': palette, 'ai_generated': ai_generated}
    write_json(folder / (name + '.json'), meta)
    return meta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1', help='Use 0.0.0.0 for access from your local network.')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    STATE.mkdir(parents=True, exist_ok=True)
    for path in sorted(STATE.glob('*.json'), key=lambda p: p.stat().st_mtime):
        try:
            job = read_json(path)
            if 'status' not in job:
                continue
            if job['status'] in ('queued', 'running'):
                job.update(status='failed', stage='Interrupted by a server restart. Start the operation again.')
            JOBS[job['id']] = job
        except (OSError, ValueError, KeyError):
            continue
    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as error:
        parser.exit(1, f'Could not open port {args.port}: {error}. Stop the other Studio instance or choose --port {args.port + 1}.\n')
    host = '127.0.0.1' if args.host == '0.0.0.0' else args.host
    url = f'http://{host}:{server.server_port}/#token={TOKEN}'
    print(f'\nPuzzle Studio\n{url}\n\nKeep this terminal open. Press Ctrl+C to stop.', flush=True)
    if args.host == '0.0.0.0':
        print('For another device, replace 127.0.0.1 with this computer’s LAN IP. Keep the token in the link private.', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for job in JOBS.values():
            if job['status'] in ('queued', 'running'):
                job['cancel'] = True
        server.server_close()
        WORKER.shutdown(wait=True)


if __name__ == '__main__':
    main()
