from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backlot import studio_motion_preferred as preferred
from backlot import studio_template_library as library
from backlot import studio_api
from backlot.studio import Studio, TEMPLATES
from backlot import motion_replay_production as production


def test_eighteen_unique_preferred_routes_are_supported_and_preserve_history():
    choices = preferred.production_map()
    assert len(choices) == 18
    cards = [r for r in library.library()['templates'] if r.get('preferred_production')]
    assert len(cards) == len({r['id'] for r in cards}) == 18
    for row in cards:
        value = row['preferred_production']
        assert value['production_contract'] in production.PRODUCERS
        assert value['source_kind'] == row['source_kind'] == 'public-source-production'
        assert value['sources_verified'] is False and row['replay']['renderer']['execution'] == 'supported'
        assert value['version'] in value['historical_versions']
        assert row['poster'] and 'href' not in row
    by_id = {v['template_id']: v for v in choices.values()}
    for key in ['template-01-integrated','template-02-expanded','template-04-dark-console','template-03-native']:
        assert by_id[key]['version'] == '1.0.1-public.2'
    assert by_id['vibrant-poster']['production_contract'] == 'haike.motion-public-poster-production/3'
    assert all(v['production_contract'] not in {'haike.motion-public-quote-production/3','haike.motion-public-paper-production/3'} for v in choices.values())


def test_missing_inputs_are_explicit_for_every_style_without_queue_or_provider(tmp_path, monkeypatch):
    from backlot.production_queue import ProductionQueue
    monkeypatch.setattr(ProductionQueue,'__init__',lambda *a,**k:pytest.fail('readonly checks created production queue'))
    app=FastAPI(); app.include_router(studio_api.router); client=TestClient(app)
    for row in preferred.preferences():
        result=client.post(f"/api/studio/template-library/{row['gallery_id']}/prepare",json={'request':{}})
        assert result.status_code == 200
        assert result.json()['status'] == 'blocked' and result.json()['submitted'] is False
        assert result.json()['required_inputs'] == row['required_inputs']
    assert client.post('/api/studio/template-library/unknown/prepare',json={'request':{}}).status_code == 409
    row=preferred.preferences()[0]
    assert client.post(f"/api/studio/template-library/{row['gallery_id']}/prepare",json={'request':{},'version':'arbitrary'}).status_code == 422


def test_motion_selection_draft_keeps_audio_materials_and_cannot_enter_basic_paid_route(tmp_path, monkeypatch):
    s=Studio(tmp_path/'projects')
    row=preferred.preferences()[0]
    selected={k:row[k] for k in ['gallery_id','template_id','version','production_contract']}
    original={'soundMode':'audio','audio':{'id':'original-audio'},'portrait':{'id':'original-portrait'},
              'ai':{'materials':[{'id':'kept-material','offset':2.1}]},'rate':1.1,'motion_production':selected}
    saved=s.save_draft({'template_id':next(t['id'] for t in TEMPLATES if t['kind']=='avatar'),
                        'text':'保留原文案','input':deepcopy(original)})
    assert saved['input'] == original and s.draft(saved['id'])['input'] == original
    app=FastAPI();app.state.studio=s;app.include_router(studio_api.router);client=TestClient(app)
    from backlot import studio_avatar
    monkeypatch.setattr(studio_avatar,'quote',lambda *a,**k:pytest.fail('selected motion entered paid basic quote'))
    monkeypatch.setattr(studio_avatar,'frozen_request',lambda *a,**k:pytest.fail('selected motion entered basic production'))
    for endpoint in ['quote','generate']:
        response=client.post(f"/api/studio/drafts/{saved['id']}/{endpoint}",json={'revision':saved['revision'],'confirmed':True})
        assert response.status_code == 409 and '动效模板' in response.json()['detail']
    assert s.draft(saved['id'])['input'] == original


def test_selection_cannot_pick_commands_or_conflicting_template():
    row=preferred.preferences()[0];value={k:row[k] for k in ['gallery_id','template_id','version']}
    for wrong in [{**value,'module':'os.system'},{**value,'template_id':'vibrant-poster'}]:
        with pytest.raises(ValueError): preferred.selection(wrong)
