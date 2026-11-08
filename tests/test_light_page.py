"""TEST fixture: the light page must preserve text and existing issue behavior."""
import copy
import json
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import core, draft_input, flip, sheet, page, daily
from geo import Geo


def fixture(light=None):
    meta = {'schema_version': 1, 'issue_date': '2099-01-01', 'title': core.SUBTITLE,
            'layout': {'schema_version': 1, 'template': 'claude-flip-v1', 'order': ['a', 'b'],
                       'stories': [{'story_id': s, 'components': []} for s in ['a', 'b']]}}
    info = {'id': 'b', 'number': 2, 'category': '语言', 'light': light if light is not None else
            {'category_fr': 'Curiosité linguistique', 'word': 'serendipity', 'gloss': 'TEST 偶然发现'}}
    body = f'''# {core.SUBTITLE} 2099-01-01
<!-- story {{"id":"a","number":1,"category":"TEST"}} -->
## TEST 主新闻
<!-- block a-h heading -->
### 今天发生了什么
<!-- block a-p paragraph -->
TEST 新闻正文。
<!-- sources -->
<!-- endstory -->
<!-- story {json.dumps(info, ensure_ascii=False)} -->
## TEST 你没在找的东西
<!-- block b-p paragraph -->
TEST 纸片正文。
<!-- block b-q paragraph -->
**TEST 另一个段落。**
<!-- sources -->
[TEST 来源](https://example.org/test?a=1&b=2)
<!-- endstory -->
'''
    return '---\n' + json.dumps(meta, ensure_ascii=False) + '\n---\n' + body


class LightPageTests(unittest.TestCase):
    def test_light_parses_and_renders_without_labels_or_lost_text(self):
        raw = fixture()
        doc, rep = draft_input.parse(raw, 'TEST')
        self.assertEqual(rep.errors, [], list(rep.lines()))
        day = doc['days'][0]
        self.assertEqual(day['items'][-1]['kind'], 'light')
        geo = Geo()
        layout, rep = sheet.load(None, day, geo, {})
        self.assertEqual(rep.errors, [])
        html = flip.render_flip_day(geo, day, layout, {'standalone': True}, 'TEST')
        self.assertEqual(page.verify(day, html), [])
        self.assertEqual(daily.audit_html(raw, html, day)['source_links'], 1)
        self.assertIn('pg-light', html)
        self.assertIn('Curiosité linguistique', html)
        self.assertIn('data:image/png;base64,', html)
        self.assertNotIn('COLLECTION', html)
        self.assertNotIn('class="kicker"', html.split('id="p2"')[1])
        self.assertIn('<a class="to-toc" href="#p0">', html)

    def test_light_minimal_fields_and_empty_sources(self):
        doc, rep = draft_input.parse(fixture({'category_fr': 'Humour'}).replace('[TEST 来源](https://example.org/test?a=1&b=2)', ''), 'TEST')
        self.assertEqual(rep.errors, [])
        self.assertNotIn('word', doc['days'][0]['items'][-1]['light'])

    def test_reject_invalid_and_conflicting_light_metadata(self):
        for value in [True, {}, {'category_fr': ''}, {'category_fr': '<b>bad</b>'},
                      {'category_fr': 'Humour', 'surprise': 'lost'}, {'category_fr': 'Humour', 'word': 9}]:
            with self.subTest(value=value):
                self.assertTrue(draft_input.parse(fixture(value), 'TEST')[1].errors)
        raw = fixture().replace('"light":', '"exploration": true, "light":')
        self.assertTrue(draft_input.parse(raw, 'TEST')[1].errors)

    def test_extra_light_story_reports_error_instead_of_crashing(self):
        raw = fixture(); _, meta, body = raw.split('---\n', 2)
        meta = json.loads(meta)
        meta['layout']['order'].pop(); meta['layout']['stories'].pop()
        raw = '---\n' + json.dumps(meta) + '\n---\n' + body
        self.assertTrue(draft_input.parse(raw, 'TEST')[1].errors)

    def test_light_and_explore_share_one_last_slot(self):
        doc, rep = draft_input.parse(fixture(), 'TEST')
        day = doc['days'][0]
        extra = copy.deepcopy(day['items'][-1]); extra['kind'] = 'explore'
        day['items'].append(extra)
        report = core.Report('TEST'); core.validate(doc, report)
        self.assertTrue(report.errors)
        day['items'] = [day['items'][1], day['items'][0]]
        report = core.Report('TEST'); core.validate(doc, report)
        self.assertTrue(report.errors)

    def test_light_fonts_embed_deterministically_and_non_latin_word_falls_back(self):
        from font_subset import embed
        raw = fixture({'category_fr': 'Clin d’œil', 'word': '木漏れ日'})
        doc, rep = draft_input.parse(raw, 'TEST'); self.assertEqual(rep.errors, [])
        day=doc['days'][0]; geo=Geo(); layout,_=sheet.load(None,day,geo,{})
        html=flip.render_flip_day(geo,day,layout,{'standalone':True},'TEST')
        one,info=embed(html, ROOT/'tools/fonts'); two,_=embed(html, ROOT/'tools/fonts')
        self.assertEqual(one,two)
        self.assertEqual(len(info),4)
        self.assertEqual(one.count('data:font/woff;base64,'),4)
        self.assertIn('Copyright (c) 2026 BaxterL',one)
        daily.audit_html(raw,one,day)

    def test_existing_editions_do_not_load_light_resources(self):
        doc, rep, raw = core.parse_file(ROOT / 'editions/2026-11-08/原稿_2026-11-08.md')
        day=doc['days'][0]; geo=Geo(); layout,_=sheet.load(None,day,geo,{})
        html=flip.render_flip_day(geo,day,layout,{'standalone':True},'TEST')
        self.assertNotIn('Daily WenKai',html)
        self.assertNotIn('data:image/png',html)
