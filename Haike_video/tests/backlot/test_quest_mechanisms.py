"""Object identity and semantic-clock checks, separate from real visual review."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from backlot import quest_vlog as quest
from backlot.work_catalog import WorkError


def scene(kind, *, items=None, cues=None, **extra):
    return {'id':'fixture','from':0,'frames':240,'module':'quest','title':'隔离动作测试',
            'quest':{'kind':kind,'items':items or [],'cues':cues or [],**extra}}


def test_rank_order_cannot_drop_duplicate_or_invent_items():
    row = scene('ranking', items=['甲','乙','丙'], cues=[15,16,17],
                ranking={'note':'隔离示意，非实际排名','orders':[{'at':60,'order':[2,0,1]}]})
    assert quest.scene(row, set()) == set()
    for order in [[2,0,0], [2,0], [2,0,3], [True,0,2]]:
        changed=deepcopy(row);changed['quest']['ranking']['orders'][0]['order']=order
        with pytest.raises(WorkError, match='同一组条目'):
            quest.scene(changed, set())
    row['quest']['ranking']['orders'][0]['at']=220
    with pytest.raises(WorkError, match='移动和阅读'):
        quest.scene(row, set())


def test_typed_question_is_authored_action_and_proof_cannot_precede_it():
    row=scene('comment', comment={'author':'隔离演示','body':'这只是自拟提问','from':15,'until':90,
                                 'photoIds':['a','b'],'proofFrom':105})
    assert quest.scene(row, {'a','b'}) == {'a','b'}
    row['quest']['comment']['proofFrom']=60
    with pytest.raises(WorkError, match='完整提问之后'):
        quest.scene(row, {'a','b'})
    row['quest']['comment']['proofFrom']=105;row['quest']['comment']['photoIds']=['missing']
    with pytest.raises(WorkError, match='已审素材'):
        quest.scene(row, {'a','b'})
    row['quest']['comment'].update(proofFrom=205,photoIds=['a','b'])
    with pytest.raises(WorkError, match='保留阅读'):
        quest.scene(row, {'a','b'})


def test_path_continuity_requires_same_graph_and_explicit_reset():
    first=scene('path', items=['知道','体验','再尝试'], cues=[30,90],
                path={'id':'same-graph','stops':[1,2]})
    second=scene('path', items=['知道','体验','再尝试'], cues=[30],
                 path={'id':'same-graph','stops':[2]})
    second.update(id='second', **{'from':240})
    for row in [first,second]:quest.scene(row,set())
    quest.continuity([first,second])
    second['quest']['path']['initial']=0
    with pytest.raises(WorkError, match='静默回到起点'):
        quest.continuity([first,second])
    second['quest']['path']['reset']=True;quest.continuity([first,second])
    second['quest']['items'][1]='换掉节点'
    with pytest.raises(WorkError, match='节点含义'):
        quest.continuity([first,second])


def test_path_movement_has_actual_travel_and_reading_windows():
    row=scene('path',items=['一','二','三'],cues=[30,40],path={'id':'route','stops':[0,2]})
    with pytest.raises(WorkError,match='移动不能重叠'):
        quest.scene(row,set())
    row['quest']['cues']=[30,210]
    with pytest.raises(WorkError,match='结果阅读'):
        quest.scene(row,set())
    row['quest']['path']=[]
    with pytest.raises(WorkError,match='路径参数须为对象'):
        quest.scene(row,set())


def test_evidence_media_does_not_replace_or_reset_the_path():
    first=scene('path',items=['知道AI','亲手体验'],cues=[30,90],path={'id':'route','stops':[0,1]})
    first['mediaId']='robot'
    second=deepcopy(first)
    second.update(id='next',**{'from':240})
    second['quest']['path']['stops']=[1];second['quest']['cues']=[30]
    second['mediaId']='store'
    assert quest.scene(first,{'robot','store'})=={'robot'}
    assert quest.scene(second,{'robot','store'})=={'store'}
    quest.continuity([first,second])
    with pytest.raises(WorkError,match='素材不存在'):
        quest.scene(first,{'store'})
    second['quest']['path']['initial']=0
    with pytest.raises(WorkError,match='静默回到起点'):
        quest.continuity([first,second])


def test_real_node_motion_state_keeps_ids_and_does_not_complete_skipped_nodes(tmp_path):
    node=shutil.which('node')
    if not node:pytest.skip('Node unavailable; the real renderer test is not mocked')
    module=Path(__file__).resolve().parents[2]/'templates/hum-production-v1/quest/MotionState.ts'
    case=[scene('path',items=['一','二','三'],cues=[30],path={'id':'route','stops':[2]}),
          scene('path',items=['一','二','三'],cues=[30],path={'id':'route','stops':[2]})]
    case[1].update(id='next',**{'from':240})
    data=tmp_path/'case.json';data.write_text(json.dumps(case),encoding='utf-8')
    code="""import {rankPositions,pathAt} from MODULE;
import fs from 'node:fs';const s=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));
console.log(JSON.stringify({rank:rankPositions(3,[{at:60,order:[2,0,1]}],78),
moving:pathAt(s,0,42),arrived:pathAt(s,0,100),handoff:pathAt(s,1,240)}));""".replace('MODULE',json.dumps(module.as_uri()))
    result=subprocess.run([node,'--input-type=module','-e',code,str(data)],capture_output=True,text=True,check=True)
    v=json.loads(result.stdout)
    assert v['rank']==[1,2,0]  # indexed by original item, not current row
    assert v['moving']['position']==1 and v['moving']['visited']==[0]
    assert v['arrived']['position']==2 and v['arrived']['visited']==[0,2]
    assert v['handoff']['position']==2 and v['handoff']['visited']==[0,2]
