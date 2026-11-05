"""The read-only gallery must not expose arbitrary files or become a draft template."""
import json
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backlot import studio_template_library as library
from backlot.studio_api import router
from backlot import studio_motiongit as motion


def test_inventory_has_unique_ids_and_existing_guides():
    items = library.entries()
    assert len(items) >= 37
    assert len({i['id'] for i in items}) == len(items)
    for item in items:
        assert library.document(item['id']).is_file(), item['id']
    for number in range(18, 22):
        item = library.entry(f'store-footage-{number}')
        assert item['status'] == '完整版'
        guide = library.document(item['id']).read_text(encoding='utf-8')
        assert 'BGM' in guide and '20Mbps' in guide
        if number >= 20:
            assert '只替换left主窗' in guide and '0.2秒网格' in guide


def test_number_four_is_discoverable_without_claiming_one_click_production(tmp_path, monkeypatch):
    monkeypatch.setattr(library, 'BINDINGS', tmp_path / 'no-private-binding.json')
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    data = client.get('/api/studio/template-library').json()
    item = next(t for t in data['templates'] if t['id'] == 'field-notes-v1')
    assert item['name'].startswith('动效模板4')
    assert item['group'] == '动画模板' and item['avatar_role'] == 'supporting-window'
    assert item['sample'] is None and 'href' not in item
    guide = client.get(item['guide']).json()['text']
    assert '--template-id field-notes-v1' in guide
    assert '2094449979141218305' in guide and '有声' in guide


def test_portable_without_private_packages_still_lists_the_eight_original_styles(tmp_path, monkeypatch):
    monkeypatch.setattr(motion, 'STORE', tmp_path / 'no-personal-store')
    monkeypatch.setattr(library, 'BINDINGS', tmp_path / 'no-media.json')
    monkeypatch.setattr(library, 'COVERS', tmp_path / 'no-private-covers')
    data = library.library()['templates']
    imported = [row for row in data if row.get('template_id') in {
        r['template_id'] for r in json.loads(library.PRESENTATION.read_text('utf-8'))['templates']}]
    assert len(imported) == 8
    assert sum(row['category'] == '动效模板' for row in data) == 18
    assert all(row['package_installed'] is False and row['status'] == '可准备本期输入'
               and row['source_kind'] == 'public-source-production' for row in imported)
    assert all(not row['reference_preview'] or row['reference_preview'].startswith('https://media.openaicut.com/') for row in imported)
    assert {row['template_id'] for row in imported if not row['reference_preview']} <= {
        'knowledge-explainer-sketchnote', 'knowledge-explainer-chalkboard'}
    assert all(row['presentation_dependency'] in {'public_original_reference', 'local_original_cover'} for row in imported)
    assert all('package_id' not in row and 'href' not in row and row['preferred_production'] for row in imported)


def test_missing_package_presentation_cannot_add_private_or_credential_preview_urls(tmp_path, monkeypatch):
    source = json.loads(library.PRESENTATION.read_text(encoding='utf-8'))
    for url in ['http://127.0.0.1/private.mp4', 'https://media.openaicut.com@other.example/style.mp4',
                'https://media.openaicut.com/style.mp4?token=private']:
        source['templates'][0]['reference_preview'] = url
        path = tmp_path / 'presentation.json'
        path.write_text(json.dumps(source, ensure_ascii=False), encoding='utf-8')
        monkeypatch.setattr(library, 'PRESENTATION', path)
        rows = library._uninstalled_motion_entries([])
        assert len(rows) == 8 and rows[0]['reference_preview'] is None


def test_installed_original_style_is_not_duplicated_by_portable_presentation(tmp_path, monkeypatch):
    first = json.loads(library.PRESENTATION.read_text(encoding='utf-8'))['templates'][0]
    store = tmp_path / 'store'
    store.mkdir()
    (store / 'registry.sqlite3').write_bytes(b'fixture sentinel; packages call is mocked')
    monkeypatch.setattr(motion, 'STORE', store)
    monkeypatch.setattr(motion, 'packages', lambda: {'packages': [{
        'id': first['gallery_id'].removeprefix('motion-package-'), 'template_id': first['template_id'],
        'version': first['version'], 'name': first['name'], 'runtime': 'native',
        'verification': 'unverified', 'runnable': False, 'workflows': {}}]})
    rows = library._imported_entries()
    assert len(rows) == 8 and len({row['id'] for row in rows}) == 8
    assert sum(row.get('package_installed') is False for row in rows) == 7


def test_private_media_is_explicit_read_only_and_range_capable(tmp_path, monkeypatch):
    monkeypatch.setattr(library, 'COVERS', tmp_path / 'no-distributed-covers')
    media = tmp_path / 'sample.mp4'
    media.write_bytes(b'0123456789')
    secret = tmp_path / 'secret.txt'
    secret.write_text('do-not-expose')
    bindings = tmp_path / 'bindings.json'
    bindings.write_text(json.dumps({'store-footage-20': {'sample': str(media), 'poster': str(secret)}}))
    monkeypatch.setattr(library, 'BINDINGS', bindings)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    result = client.get('/api/studio/template-library')
    assert result.status_code == 200
    assert str(tmp_path) not in result.text
    assert 'secret.txt' not in result.text
    poster = client.get('/api/studio/template-library/store-footage-20/media/poster')
    assert poster.status_code == 200  # The verified source cover is a safe fallback.
    assert poster.headers['content-type'].startswith('image/')
    assert secret.read_bytes() not in poster.content
    assert client.get('/api/studio/template-library/unknown/media/sample').status_code == 404
    assert client.get('/api/studio/template-library/store-footage-20/media/secret.txt').status_code == 404
    response = client.get('/api/studio/template-library/store-footage-20/media/sample', headers={'Range': 'bytes=2-5'})
    assert response.status_code == 206 and response.content == b'2345'
    assert client.get('/api/studio/template-library/store-footage-20/guide').json()['text'].startswith('# 店长')
    assert client.get('/api/studio/template-library/unknown/guide').status_code == 404


def test_document_stays_in_template_or_runbook_roots(monkeypatch):
    monkeypatch.setattr(library, 'entry', lambda _: {'runbook': '.local/private.md'})
    assert library.document('anything') is None


def test_portable_covers_work_without_private_bindings(tmp_path, monkeypatch):
    covers = tmp_path / 'relocated-package' / 'covers'
    covers.mkdir(parents=True)
    poster = covers / 'store-footage-20.jpg'
    poster.write_bytes(b'portable screenshot fixture')
    monkeypatch.setattr(library, 'COVERS', covers)
    monkeypatch.setattr(library, 'BINDINGS', tmp_path / 'missing-private-map.json')
    assert library.media('store-footage-20', 'poster') == poster
    assert library.media('store-footage-20', 'sample') is None
    assert library.media('../store-footage-20', 'poster') is None
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    listing = client.get('/api/studio/template-library').json()['templates']
    item = next(t for t in listing if t['id'] == 'store-footage-20')
    assert item['poster'] and item['sample'] is None
    assert client.get(item['poster']).content == poster.read_bytes()


def test_stale_or_malformed_private_binding_falls_back_to_portable_cover(tmp_path, monkeypatch):
    monkeypatch.setattr(library, 'COVERS', tmp_path)
    poster = tmp_path / 'store-footage-20.jpg'
    poster.write_bytes(b'fixture')
    bindings = tmp_path / 'bindings.json'
    monkeypatch.setattr(library, 'BINDINGS', bindings)
    for content in ('invalid JSON', '[]', '{"store-footage-20": null}',
                    json.dumps({'store-footage-20': {'poster': 'missing.jpg'}})):
        bindings.write_text(content)
        assert library.media('store-footage-20', 'poster') == poster


def test_png_original_cover_survives_relocation_without_conversion(tmp_path, monkeypatch):
    monkeypatch.setattr(library, 'COVERS', tmp_path / 'relocated')
    monkeypatch.setattr(library, 'BINDINGS', tmp_path / 'missing.json')
    library.COVERS.mkdir()
    cover = library.COVERS / 'avatar-interview-v7.png'
    cover.write_bytes(b'original PNG bytes')
    assert library.media('avatar-interview-v7', 'poster') == cover
    assert library.media('../avatar-interview-v7', 'poster') is None


def test_imported_motion_enters_gallery_as_metadata_without_executing_or_leaking(tmp_path, monkeypatch):
    monkeypatch.setattr(motion, 'STORE', tmp_path / 'motion-private')
    monkeypatch.setattr(motion, 'helper_command', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('gallery executed helper')))
    motion._put_package({'id':'mg-gallery-known','name':'隔离原生模板','template_id':'fixture-native','version':'1.0',
        'runtime':'motiongit-host/1','verification':'verified','runnable':True,'support':'official-helper',
        'path':'C:/private/source.motion','personal_key':'never-expose-this-value',
        'workflows':{'motion-kit':{'schema':{'default':{'private':'never-expose-this-value'}},
                                    'controls':{'one':{'label':'控件一'},'two':{'label':'控件二'}}}}})
    motion._put_package({'id':'mg-gallery-unknown','name':'未核验模板','template_id':'fixture-unknown','version':'9.0',
        'verification':'pending','runnable':False,'support':'inspection-only','workflows':{}})
    data=library.library();known=next(t for t in data['templates'] if t.get('package_id')=='mg-gallery-known')
    unknown=next(t for t in data['templates'] if t.get('package_id')=='mg-gallery-unknown')
    assert known['source_kind']=='imported-motion' and known['group']=='已导入 .motion'
    assert known['href']=='/motiongit?section=packages&package=mg-gallery-known'
    assert known['capability_status']=='开放制作接口' and known['declared_control_count']==2
    assert unknown['capability_status']=='待核验，仅检查'
    assert library.document(known['id']).is_file()
    rendered=json.dumps(data,ensure_ascii=False)
    assert 'never-expose-this-value' not in rendered and 'C:/private' not in rendered
    assert not {'workflows','schema','path','personal_key'} & set(known)


def test_verified_future_native_protocol_is_not_promoted_to_production(tmp_path, monkeypatch):
    monkeypatch.setattr(motion,'STORE',tmp_path/'motion-private')
    motion._put_package({'id':'mg-future-only','name':'未来协议','template_id':'fixture-future','version':'9.9',
        'verification':'verified','runnable':True,'support':'official-helper',
        'workflows':{'native':{'schema':{},'production_protocol':'unsupported-future'}}})
    card=next(t for t in library.entries() if t.get('package_id')=='mg-future-only')
    assert card['capability_status']=='仅参数编辑'


def test_gallery_does_not_create_a_motion_store_when_none_was_imported(tmp_path, monkeypatch):
    monkeypatch.setattr(motion,'STORE',tmp_path/'not-created')
    monkeypatch.setattr(motion,'packages',lambda: (_ for _ in ()).throw(AssertionError('empty gallery read created registry')))
    assert library.entries() and not motion.STORE.exists()


def test_gallery_has_two_categories_and_formal_six_keep_historical_media_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(motion, 'STORE', tmp_path / 'no-imports')
    cards = library.library()['templates']
    assert {t['category'] for t in cards} == {'固定模板', '动效模板'}
    for identity in ['chromatic-06', 'chromatic-07', 'chromatic-08', 'chromatic-09', 'chromatic-six-10', 'chromatic-six-11']:
        item = next(t for t in cards if t['id'] == identity)
        assert item['category'] == '动效模板' and item['version'] == '1.1.0'
        assert item['render_profile']['audio_required'] is True
        assert item['render_profile']['silent'] is False
        assert item['render_profile']['width'] == 1080
        assert item['render_profile']['height'] == 1920
        assert '不重渲染' in item['description']
        assert 'href' not in item  # Gallery approval does not create a one-click production adapter.
        assert library.document(identity).name == 'FORMAL.md'


def test_real_static_import_appears_as_inspection_only_without_extra_registration(tmp_path, monkeypatch):
    monkeypatch.setattr(motion,'STORE',tmp_path/'motion-private')
    monkeypatch.setattr(motion,'helper_command',lambda *a,**kw: (_ for _ in ()).throw(AssertionError('static gallery import executed helper')))
    source=tmp_path/'future.motion'
    with zipfile.ZipFile(source,'w') as archive:
        archive.writestr('motion.json',json.dumps({'format':'motiongit-template','specVersion':'0.1.0-draft.1',
            'template':{'id':'future-static','name':'隔离未来模板','version':'1.0'},'runtime':{'profile':'html-canvas/1'},
            'parameters':{'schema':'params.schema.json'}}))
        archive.writestr('params.schema.json',json.dumps({'type':'object','properties':{'title':{'type':'string'}}}))
    imported=motion.import_package(source)
    card=library.entry('motion-package-'+imported['id'])
    assert card['name']=='隔离未来模板' and card['capability_status']=='待核验，仅检查'
    media=tmp_path/'local-film.mp4';media.write_bytes(b'0123456789')
    bindings=tmp_path/'bindings.json';bindings.write_text(json.dumps({card['id']:{'sample':str(media)}}))
    monkeypatch.setattr(library,'BINDINGS',bindings)
    app=FastAPI();app.include_router(router);client=TestClient(app)
    item=next(t for t in client.get('/api/studio/template-library').json()['templates'] if t['id']==card['id'])
    assert item['status']=='本机开发样片' and item['capability_status']=='待核验，仅检查'
    # An explicit local sample cannot promote an unverified execution protocol.
    response=client.get(item['sample'],headers={'Range':'bytes=2-5'})
    assert response.status_code==206 and response.content==b'2345'
