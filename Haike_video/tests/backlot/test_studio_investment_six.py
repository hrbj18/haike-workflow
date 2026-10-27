from copy import deepcopy

import pytest

from backlot.studio_investment_six import validate_props
from backlot.work_catalog import WorkError


def props():
    return dict(style=11, durationFrames=796, audio='master.wav', closingFrom=700,
                avatar=dict(src='avatar.mp4', **{'from': 0}, frames=144),
                shots=[dict(id=f'{lane}{j}', lane=lane, src=f'{j}.mp4', **{'from': start},
                            frames=min(120, 796-start), offset=0)
                       for lane in ('left', 'right') for j, start in enumerate(range(0, 796, 120))],
                captions=[dict(text='先看门店，再谈合作。', startMs=500, endMs=3000)],
                chapters=[dict(**{'from': 0}, title='先看门店\n再谈合作', sub='现场了解', points=['看产品'])])


@pytest.mark.parametrize('style', [7, 8, 9, 11, 12, 13])
def test_natural_clock_and_all_six_styles(style):
    p = props()
    p['style'] = style
    validate_props(p)


@pytest.mark.parametrize('mutation', ['gap', 'late_avatar', 'long_caption', 'long_title', 'outside_caption'])
def test_rejects_unrenderable_or_out_of_scope_inputs(mutation):
    p = deepcopy(props())
    if mutation == 'gap': p['shots'][1]['from'] += 1
    if mutation == 'late_avatar': p['avatar']['from'] = 2
    if mutation == 'long_caption': p['captions'][0]['text'] = '字' * 19
    if mutation == 'long_title': p['chapters'][0]['title'] = '字' * 9
    if mutation == 'outside_caption': p['captions'][0]['endMs'] = 30000
    with pytest.raises(WorkError):
        validate_props(p)
