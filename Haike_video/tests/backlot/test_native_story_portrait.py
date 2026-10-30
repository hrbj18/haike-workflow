"""Real-font overflow guards; fixture text is not a production visual review."""
from pathlib import Path
from copy import deepcopy
import pytest

from backlot import studio_native_story_portrait as story
from backlot.work_catalog import WorkError


@pytest.fixture
def fitted():
    font=next((p for p in [Path('C:/Windows/Fonts/msyh.ttc'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')] if p.is_file()),None)
    if not font:pytest.skip('No real test font installed')
    a={'headlineFirst':'一起体验','headlineConnector':'来','headlineAccent':'试试','statementFirst':'近距离看','statementSecond':'亲手操作','payoffFirst':'一起','payoffAccent':'来吧'}
    b={'scopePrefix':'带孩子','scopeSubject':'来海客','scopeAccent':'亲手体验','scopeConclusion':'AI',
       'templateLine':'来现场试试','categories':['看','摸','用','玩'],'categoryNotes':['实拍']*4}
    c={'actionText':'这个周末，带孩子来体验','brandTitle':'海客AI社区服务店','brandDescription':'未来汇一楼'}
    return {'s01':a,'s04':b,'s08':c},{'body':font,'display':font}


def test_actual_font_accepts_bounded_story_copy(fitted):
    contents,fonts=fitted
    story._text_gate(contents,fonts)


@pytest.mark.parametrize('group,key',[('s01','headlineFirst'),('s04','scopeAccent'),('s08','actionText'),('s08','brandDescription')])
def test_new_long_copy_is_blocked_before_render_instead_of_clipping(fitted,group,key):
    contents,fonts=fitted;contents=deepcopy(contents);contents[group][key]='W'*120
    with pytest.raises(WorkError,match='字框'):
        story._text_gate(contents,fonts)


def test_category_label_and_note_share_their_real_cell_width(fitted):
    contents,fonts=fitted;contents['s04']['categories'][0]='W'*60
    with pytest.raises(WorkError,match='四卡标签'):
        story._text_gate(contents,fonts)
