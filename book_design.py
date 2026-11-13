"""Customizable print renderer; puzzle algorithms remain in the original engine."""
import argparse
import json
import math
from pathlib import Path
import random
import re
from datetime import date

from PIL import Image, ImageDraw, ImageFont, ImageOps
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
import mazes
import sudoku
import wordsearch
from font_support import font_path
from studio_catalog import DEFAULT_DESIGN, LAYOUTS, PATTERNS

ROOT = Path(__file__).resolve().parent
FONTS = {'sans': 'Arial.ttf', 'serif': 'Georgia Bold.ttf', 'mono': 'Courier New Bold.ttf'}


def validate(value):
    if not isinstance(value, dict):
        raise ValueError('Design must be an object.')
    d = {**DEFAULT_DESIGN, **{k: v for k, v in value.items() if k in DEFAULT_DESIGN}}
    for key in ('bg', 'ink', 'accent', 'highlight'):
        if not isinstance(d[key], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', d[key]):
            raise ValueError(f'{key}: use a six-digit hex color.')
    for key, choices in [('font', FONTS), ('layout', LAYOUTS), ('pattern', PATTERNS), ('title_align', ['left','center'])]:
        if d[key] not in choices:
            raise ValueError('Invalid ' + key)
    for key, low, high in [('margin',54,90), ('font_size',12,26), ('grid_size',10,22), ('word_columns',2,4),
                           ('image_x',0,100), ('image_y',0,100), ('image_zoom',100,200), ('image_opacity',0,100)]:
        if isinstance(d[key], bool) or not re.fullmatch(r'\d+', str(d[key])) or not low <= int(d[key]) <= high:
            raise ValueError(f'{key} must be between {low} and {high}.')
        d[key] = int(d[key])
    if d['solution_density'] not in (1,4,6):
        raise ValueError('Choose 1, 4, or 6 solutions per page.')
    for key in ('gridlines','reverse','diagonal','color_interior','include_solutions','include_intro','page_numbers'):
        if not isinstance(d[key], bool):
            raise ValueError('Invalid switch: ' + key)
    for key in ('dedication','instructions'):
        if not isinstance(d[key], str) or len(d[key]) > 1000:
            raise ValueError(key + ' must be text up to 1000 characters.')
    if d['image'] and not re.fullmatch(r'[a-f0-9]{32}\.png', str(d['image'])):
        raise ValueError('Invalid artwork identifier.')
    if d['image'] and not (ROOT / 'out' / 'assets' / d['image']).is_file():
        raise ValueError('Artwork is missing. Upload it again.')
    return d


def setup_words(d):
    directions = [(0,1),(1,0)]
    if d['diagonal']:
        directions.extend([(1,1),(1,-1)])
    if d['reverse']:
        directions += [(-r,-c) for r,c in directions.copy()]
    wordsearch.DIRS = directions


def puzzles(config):
    d = validate(config.get('design', {}))
    setup_words(d)
    rng = random.Random(config['seed'])
    random.seed(config['seed'])
    if config['kind'] == 'wordsearch':
        for puzzle in config['theme_data']['puzzles'][:config['count']]:
            grid, paths, words = wordsearch.generate_puzzle(puzzle['words'], d['grid_size'])
            yield {'kind':'wordsearch','name':puzzle['name'],'grid':grid,'paths':paths,'words':words}
    else:
        ratios = {'easy':(.7,.3),'mixed':(.4,.35),'hard':(0,.4)}[config['profile']]
        easy, medium = (int(config['count'] * r) for r in ratios)
        levels = ['easy']*easy + ['medium']*medium + ['hard']*(config['count']-easy-medium)
        rng.shuffle(levels)
        for level in levels:
            if config['kind'] == 'sudoku':
                solved = sudoku.make_solved(rng)
                yield {'kind':'sudoku','name':level.title() + ' Sudoku','grid':sudoku.make_puzzle(solved,level,rng),'solution':solved}
            else:
                n = {'easy':11,'medium':15,'hard':19}[level]
                walls = mazes.gen_maze(n,n,rng)
                yield {'kind':'maze','name':level.title() + ' Maze','walls':walls,'n':n,'path':mazes.solve(walls,n,n)}


def draw_puzzle(c, p, x, top, size, d, answer=False):
    n = p.get('n') or len(p['grid'])
    cell = size/n
    ink = d['ink'] if d['color_interior'] else '#222222'
    accent = d['accent'] if d['color_interior'] else '#aaaaaa'
    c.setStrokeColor(HexColor(ink)); c.setFillColor(HexColor(ink))
    if p['kind'] == 'maze':
        c.setLineWidth(max(.6,cell*.07))
        for (col,row), walls in p['walls'].items():
            xx,yy=x+col*cell,top-row*cell
            for wall in walls:
                if (col==0 and row==0 and wall=='W') or (col==n-1 and row==n-1 and wall=='E'):
                    continue
                points={'N':(xx,yy,xx+cell,yy),'S':(xx,yy-cell,xx+cell,yy-cell),'E':(xx+cell,yy,xx+cell,yy-cell),'W':(xx,yy,xx,yy-cell)}[wall]
                c.line(*points)
        if answer:
            c.setStrokeColor(HexColor(accent));c.setLineWidth(cell*.2)
            points=[(x+(col+.5)*cell,top-(row+.5)*cell) for col,row in p['path']]
            for start,end in zip(points,points[1:]):c.line(*start,*end)
        return
    if answer and p['kind']=='wordsearch':
        c.setLineCap(1);c.setLineWidth(cell*.75);c.setStrokeColor(HexColor(d['highlight'] if d['color_interior'] else '#dddddd'))
        for path in p['paths']:
            r,col=path[0];rr,cc=path[-1];c.line(x+(col+.5)*cell,top-(r+.5)*cell,x+(cc+.5)*cell,top-(rr+.5)*cell)
    if d['gridlines'] or p['kind']=='sudoku':
        for i in range(n+1):
            strong=p['kind']=='sudoku' and i%3==0
            c.setLineWidth(1.5 if strong else .35);c.setStrokeColor(HexColor(ink if strong else '#cccccc'))
            c.line(x+i*cell,top,x+i*cell,top-size);c.line(x,top-i*cell,x+size,top-i*cell)
    grid=p['solution'] if answer and p['kind']=='sudoku' else p['grid']
    font_size=min(d['font_size'],cell*.60)
    c.setFont('Studio',font_size);c.setFillColor(HexColor(ink))
    for row,values in enumerate(grid):
        for col,value in enumerate(values):
            if value:c.drawCentredString(x+(col+.5)*cell,top-(row+.5)*cell-font_size*.34,str(value))


def lines(text, measure, width):
    result=[]
    for paragraph in text.split('\n'):
        current=''
        for word in paragraph.split():
            if measure(word)>width:
                raise ValueError('A word in the title or copy is too wide to print. Add spaces or shorten it.')
            candidate=(current+' '+word).strip()
            if current and measure(candidate)>width:result.append(current);current=word
            else:current=candidate
        result.append(current)
    return result


def interior(config, out):
    d=validate(config.get('design',{})); margin=d['margin'];width=612-2*margin
    pdfmetrics.registerFont(TTFont('Studio',font_path(FONTS[d['font']])))
    c=canvas.Canvas(str(out),pagesize=(612,792));c.setTitle(config['title']);c.setAuthor(config['author'])
    ink=d['ink'] if d['color_interior'] else '#222222'
    page=0
    def heading(title, y=715, size=24):
        c.setFillColor(HexColor(ink));c.setFont('Studio',size)
        wrapped=lines(title,lambda s:pdfmetrics.stringWidth(s,'Studio',size),width)
        for line in wrapped:
            if y < margin:
                raise ValueError('Text does not fit this page. Shorten the title, dedication, or instructions.')
            if d['title_align']=='center':c.drawCentredString(306,y,line)
            else:c.drawString(margin,y,line)
            y-=size*1.35
        return y
    def finish():
        nonlocal page
        page+=1
        if d['page_numbers']:
            c.setFont('Studio',9);c.setFillColor(HexColor(ink));c.drawCentredString(306,32,str(page))
        c.showPage()
    if d['include_intro']:
        y=heading(config['title'],590,30)-20
        heading(config['subtitle'],y,14);heading(config['author'],160,16);finish()
        heading('A moment for yourself',690,25)
        instructions=d['instructions'] or {'wordsearch':'Find each word in the grid. Words follow the directions chosen for this book.','sudoku':'Fill each row, column, and 3 by 3 box with the numbers 1 through 9, without repeating a number.','maze':'Start at the opening on the top-left. Reach the bottom-right opening without crossing a wall.'}[config['kind']]
        heading(instructions,610,13)
        heading(f'Copyright © {date.today().year} {config["author"]}',150,10);finish()
    if d['dedication']:
        heading(d['dedication'],560,18);finish()
    items=[]
    for index,p in enumerate(puzzles(config),1):
        print(f'Puzzle {index}/{config["count"]}',flush=True)
        y=heading(f'{index:02d}  {p["name"]}',735,22)-18
        word_rows = math.ceil(len(p.get('words', [])) / d['word_columns'])
        size=min(width,440,y-margin-35-max(0,word_rows-1)*20)
        draw_puzzle(c,p,(612-size)/2,y,size,d)
        if p['kind']=='wordsearch':
            top=y-size-30;cols=d['word_columns'];slot=width/cols
            for k,word in enumerate(p['words']):
                fs=min(d['font_size']*.72,slot/max(1,len(word)) * 1.4,14)
                c.setFont('Studio',fs);c.setFillColor(HexColor(ink))
                c.drawCentredString(margin+(k%cols+.5)*slot,top-(k//cols)*20,word)
        finish();items.append(p)
    if d['include_solutions']:
        density=d['solution_density'];cols=1 if density==1 else 2;rows=math.ceil(density/cols)
        cell_w=width/cols;cell_h=620/rows;size=min(cell_w-24,cell_h-46)
        for start in range(0,len(items),density):
            heading('Solutions',735,24)
            for k,p in enumerate(items[start:start+density]):
                x=margin+(k%cols)*cell_w+(cell_w-size)/2;top=675-(k//cols)*cell_h
                c.setFont('Studio',11);c.drawString(x,top+15,f'Puzzle {start+k+1}')
                draw_puzzle(c,p,x,top,size,d,True)
            finish()
    if config.get('also_from'):
        y=heading('Also by '+config['author'],700,24)-20
        for book in config['also_from']:
            y=heading(book['title'],y,16)-20
            if book.get('subtitle'):y=heading(book['subtitle'],y,11)-15
            if y<150:finish();y=700
        finish()
    c.save()


def artwork(d, size):
    image=Image.new('RGB',size,d['bg']);pen=ImageDraw.Draw(image);w,h=size
    color=d['accent']
    if d['pattern']=='geometric':
        step=max(40,w//8)
        for x in range(-h,w+h,step):pen.line((x,0,x+h,h),fill=color,width=max(2,w//500))
    elif d['pattern']=='waves':
        for y in range(0,h,max(50,h//14)):
            points=[(x,y+int(math.sin(x/w*math.pi*4)*h*.035)) for x in range(0,w+1,10)]
            pen.line(points,fill=color,width=max(3,w//350))
    elif d['pattern']=='botanical':
        import cover
        for i in range(9):cover.leaf(pen,int(w*(.12+.095*i)),int(h*(.25+.5*(i%2))),max(.3,w/1800),color)
    if d['image']:
        with Image.open(ROOT/'out'/'assets'/d['image']) as source:
            art=ImageOps.fit(source.convert('RGBA'),(int(w*d['image_zoom']/100),int(h*d['image_zoom']/100)),centering=(d['image_x']/100,d['image_y']/100))
            x=int((art.width-w)*d['image_x']/100);y=int((art.height-h)*d['image_y']/100)
            art=art.crop((x,y,x+w,y+h))
            base=image.convert('RGBA')
            art.putalpha(art.getchannel('A').point(lambda alpha: int(alpha*d['image_opacity']/100)))
            image=Image.alpha_composite(base,art).convert('RGB')
    return image


def front_cover(config,out):
    d=validate(config.get('design',{}));w,h=2550,3300
    image=Image.new('RGB',(w,h),d['bg']);pen=ImageDraw.Draw(image)
    layout=d['layout']
    art_box={'framed':(240,1400,2310,2670),'minimal':(400,1650,2150,2700),'poster':(0,1250,2550,2780),
             'split':(0,0,2550,1650),'band':(160,1100,2390,2500),'gallery':(240,250,2310,1950)}[layout]
    x0,y0,x1,y1=art_box;image.paste(artwork(d,(x1-x0,y1-y0)),(x0,y0));pen=ImageDraw.Draw(image)
    if layout=='framed':pen.rectangle((110,110,w-110,h-110),outline=d['accent'],width=8)
    if layout=='band':pen.rectangle((0,180,w,340),fill=d['accent'])
    top=1830 if layout=='split' else 2100 if layout=='gallery' else 390
    max_height = {'split': 600, 'gallery': 350, 'poster': 450, 'band': 350}.get(layout, 620)
    size=160
    while size>=50:
        font=ImageFont.truetype(font_path(FONTS[d['font']]),size)
        wrapped=lines(config['title'],lambda s:pen.textlength(s,font=font),w-440)
        if len(wrapped)*size*1.25<=max_height:break
        size-=5
    if size<50:raise ValueError('Cover title is too long for this layout.')
    for line in wrapped:
        x=220 if d['title_align']=='left' else (w-pen.textlength(line,font=font))/2
        pen.text((x,top),line,font=font,fill=d['ink']);top+=int(size*1.25)
    font=ImageFont.truetype(font_path('Arial.ttf'),50)
    subtitle_lines=lines(config['subtitle'],lambda s:pen.textlength(s,font=font),w-500)
    subtitle_bottom = {'framed':1350, 'minimal':1600, 'poster':1200, 'band':1050, 'gallery':2800, 'split':2800}[layout]
    while top + 35 + len(subtitle_lines)*int(font.size*1.3) > subtitle_bottom and font.size > 26:
        font=ImageFont.truetype(font_path('Arial.ttf'),font.size-2)
        subtitle_lines=lines(config['subtitle'],lambda s:pen.textlength(s,font=font),w-500)
    if top + 35 + len(subtitle_lines)*int(font.size*1.3) > subtitle_bottom:
        raise ValueError('Subtitle does not fit this cover layout. Shorten it or choose another layout.')
    for line in subtitle_lines:
        pen.text(((w-pen.textlength(line,font=font))/2,top+35),line,font=font,fill=d['ink']);top+=int(font.size*1.3)
    font=ImageFont.truetype(font_path('Arial Bold.ttf'),60)
    badge=config.get('badge') or f'{config["count"]} PUZZLES'
    while pen.textlength(badge,font=font)>w-500:font=ImageFont.truetype(font_path('Arial Bold.ttf'),font.size-2)
    pen.rounded_rectangle((220,2850,w-220,3000),radius=18,fill=d['highlight'])
    pen.text(((w-pen.textlength(badge,font=font))/2,2880),badge,font=font,fill=d['ink'])
    author=config['author'];font=ImageFont.truetype(font_path('Arial.ttf'),55)
    while pen.textlength(author,font=font)>w-400:font=ImageFont.truetype(font_path('Arial.ttf'),font.size-2)
    pen.text(((w-pen.textlength(author,font=font))/2,3090),author,font=font,fill=d['ink'])
    image.save(out,'PNG',dpi=(300,300))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--project',required=True);parser.add_argument('--out',required=True);parser.add_argument('--cover',action='store_true')
    args=parser.parse_args();config=json.loads(Path(args.project).read_text(encoding='utf-8'))
    (front_cover if args.cover else interior)(config,Path(args.out))
