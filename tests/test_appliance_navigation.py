from html.parser import HTMLParser
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]

class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.current=None
    def handle_starttag(self,tag,attrs):
        if tag=='a': self.current={'attrs':dict(attrs),'text':''}
    def handle_data(self,data):
        if self.current is not None: self.current['text']+=data
    def handle_endtag(self,tag):
        if tag=='a' and self.current is not None:
            self.links.append(self.current); self.current=None

@pytest.mark.parametrize('label,target',[
    ('วิเคราะห์ข้อมูล','/frontend/analysis/analysis.html'),
    ('กราฟ','/frontend/analysis/analysis.html#charts'),
])
def test_appliances_analysis_navigation(label,target):
    parser=Links()
    parser.feed((ROOT/'Front__end/appliances/appliances.html').read_text(encoding='utf-8-sig'))
    links=[link for link in parser.links if link['text'].strip().endswith(label)]
    assert len(links)==1
    attrs=links[0]['attrs']
    assert attrs.get('href')==target
    # Appliances JS intercepts links with aria-disabled=true; these must be enabled.
    assert attrs.get('aria-disabled')!='true'
    assert 'disabled-link' not in attrs.get('class','').split()
    destination=ROOT/'Front__end'/target.split('#')[0].removeprefix('/frontend/')
    assert destination.is_file()
    if '#charts' in target:
        source=(ROOT/'Front__end/analysis/analysis.js').read_text(encoding='utf-8-sig')
        assert 'hashchange' in source and 'charts' in source
