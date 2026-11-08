"""固定纸片模板。只排入已写好的内容，不生成正文或每日装饰。"""
import base64
from pathlib import Path
from core import item_key
from page import esc, inline, render_blocks

ASSETS = Path(__file__).with_name('assets')


def render_light_page(item, number):
    light = item['light']
    word = f'<div class="light-word">{inline(light["word"])}</div>' if light.get('word') else ''
    gloss = f'<p class="light-gloss">{inline(light["gloss"])}</p>' if light.get('gloss') else ''
    divider = '<div class="light-divider" aria-hidden="true"></div>' if word or gloss else ''
    paragraphs = ''.join(render_blocks(s['blocks']) for s in item['sections'] if s['key'] != 'sources')
    sources = ''.join(render_blocks(s['blocks']) for s in item['sections'] if s['key'] == 'sources')
    sources = f'<div class="light-source">{sources}</div>' if sources else ''
    flower = base64.b64encode((ASSETS / 'light-botanical.png').read_bytes()).decode('ascii')
    return (f'<section class="pg pg-light" id="p{number}"><div class="pg-in">'
            '<div class="light-collage"><div class="light-back" aria-hidden="true"></div>'
            '<span class="light-tape" aria-hidden="true"></span>'
            f'<article class="light-letter" id="s-{item_key(item)}">'
            f'<img class="light-botanical" alt="" aria-hidden="true" src="data:image/png;base64,{flower}">'
            f'{word}{gloss}{divider}<h2 class="hl">{inline(item["title"])}</h2>'
            f'<div class="body"><div class="light-copy">{paragraphs}</div>{sources}</div>'
            f'<div class="light-category" lang="fr">{inline(light["category_fr"])}</div>'
            '</article></div><p class="pg-foot"><a class="to-toc" href="#p0">回到目录</a></p>'
            '</div></section>')
