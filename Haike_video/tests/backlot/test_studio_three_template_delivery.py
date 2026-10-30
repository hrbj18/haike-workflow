from copy import deepcopy

from backlot import studio_native_story_portrait as portrait


def test_opening_presenter_stops_before_wall_handoff_without_changing_source_clock():
    result={'props':{'presenter':{'src':'presenter.mp4','from':0,'frames':1824,'offset':0,'modes':[]},
                     'scenes':[{'cueTimes':{'wall_handoff':3.5}}]},
            'sources':{'presenter.mp4':'same-complete-source'},'provenance':{'presenterClips':['same-source-proof']}}
    before=deepcopy(result)
    portrait.apply_presenter_mode(result,'opening')
    assert result['props']['presenter']['modes']==[{'from':0,'frames':210,'mode':'large'},
                                                 {'from':210,'frames':1614,'mode':'hidden'}]
    assert result['sources']==before['sources'] and result['provenance']==before['provenance']
    assert result['props']['presenter']['frames']==1824 and result['props']['presenter']['offset']==0
    closing=portrait.apply_presenter_mode(deepcopy(before),'closing')
    assert closing['props']['presenter']['modes'][-1]=={'from':1524,'frames':300,'mode':'large'}
