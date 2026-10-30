"""Actual sentence clocks and original control holds, without package execution."""
from copy import deepcopy

import pytest

from backlot import studio_motion_poster_session as poster
from backlot.work_catalog import WorkError


def test_whole_sentences_and_reveal_targets_survive_a_different_speech_clock():
    segments=[{'control':'kinetic','variant':'stack','t0':0,'t1':5,'cues':[.2,2], 'props':{'lines':['甲','乙']}},
              {'control':'cta','variant':'arrow','t0':5,'t1':10,'cues':[5.2,7], 'props':{'text':'来坐坐','sub':'门店实拍'}}]
    controls={'kinetic':{'minDur':2.5,'tail':1.2},'cta':{'minDur':2.5,'tail':1.4}}
    caps=[{'t0':i*2+.2,'t1':i*2+1.8,'zh':f'句{i}'} for i in range(8)]
    original=deepcopy(segments);out,maps=poster.fit_segments(segments,caps,16,controls)
    assert segments==original and out[-1]['t1']==16 and out[0]['t1']==out[1]['t0']
    assert not any(c['t0']<out[0]['t1']<c['t1'] for c in caps)
    assert [n for row in maps for n in row['captionIndices']]==list(range(8))
    for s in out:
        assert s['t1']-s['cues'][-1]>=controls[s['control']]['tail']
        assert all(cue in [c['t0'] for c in caps] for cue in s['cues'])
    assert {b['target'] for b in maps[0]['beats']}=={'lines.0','lines.1'}
    assert {b['target'] for b in maps[1]['beats']}=={'text','sub'}


def test_too_short_speech_is_rejected_instead_of_truncating_or_retiming():
    with pytest.raises(WorkError,match='不会截句'):
        poster.fit_segments([{'control':'kinetic','t0':0,'t1':4,'cues':[0,2]}],
                            [{'t0':0,'t1':1,'zh':'只有一句'}],1,{'kinetic':{'minDur':2.5,'tail':1.2}})


def test_overlapping_captions_cannot_supply_a_fake_sentence_gap():
    with pytest.raises(WorkError,match='真实字幕时间'):
        poster.fit_segments([], [{'t0':0,'t1':2,'zh':'一'},{'t0':1,'t1':3,'zh':'二'}],3,{})


def test_real_clip_capacity_changes_the_cut_without_looping_or_splitting_speech():
    segments=[{'control':'media','t0':0,'t1':8,'cues':[.2,2]},
              {'control':'cta','t0':8,'t1':16,'cues':[8.2,10]}]
    caps=[{'t0':i*2+.2,'t1':i*2+1.8,'zh':f'句{i}'} for i in range(8)]
    controls={'media':{'minDur':3,'tail':.7},'cta':{'minDur':2.5,'tail':1.4}}
    unrestricted,_=poster.fit_segments(segments,caps,16,controls)
    bounded,maps=poster.fit_segments(segments,caps,16,controls,{0:6})
    assert unrestricted[0]['t1']>6 and bounded[0]['t1']<=6.001
    assert bounded[-1]['t1']==16 and [j for m in maps for j in m['captionIndices']]==list(range(8))
    assert not any(c['t0']<bounded[0]['t1']<c['t1'] for c in caps)
