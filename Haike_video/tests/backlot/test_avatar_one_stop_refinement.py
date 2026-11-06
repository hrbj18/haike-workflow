import base64
import io
import json
import pytest
from PIL import Image
from backlot.avatar_one_stop_refinement import TwoImageRefinement
from backlot.work_catalog import WorkError


def png(color):
    f=io.BytesIO();Image.new('RGB',(256,320),color).save(f,'PNG');return f.getvalue()


def test_two_distinct_references_are_sent_once_and_the_result_survives_restart(tmp_path):
    source=tmp_path/'person.png';source.write_bytes(png('navy'))
    reference=tmp_path/'skin.png';reference.write_bytes(png('pink'))
    calls=[]
    def transport(config,payload):
        calls.append(payload)
        return {'id':'response-fixture','status':'completed','usage':{'output_tokens':8},
                'output':[{'type':'image_generation_call','status':'completed','result':base64.b64encode(png('teal')).decode()}]}
    config=lambda:{'api_key':'fake-only','base_url':'http://fixture.invalid/v1'}
    client=TwoImageRefinement(config,transport=transport)
    result=client.run(tmp_path/'job',source,reference,'同一固定肤质')
    assert result['status']=='succeeded' and result['input_images']==2
    content=calls[0]['input'][0]['content']
    assert len(content)==3 and content[1]['image_url']!=content[2]['image_url']
    assert 'fake-only' not in (tmp_path/'job/operation.json').read_text(encoding='utf-8')
    with Image.open(tmp_path/'job/result.png') as image:assert image.size==(1024,1280) and image.mode=='RGB'
    assert TwoImageRefinement(config,transport=transport).run(tmp_path/'job',source,reference,'同一固定肤质')==result
    assert len(calls)==1
    reference.write_bytes(png('red'))
    with pytest.raises(WorkError,match='冻结'):client.run(tmp_path/'job',source,reference,'同一固定肤质')
    assert len(calls)==1


def test_uncertain_transport_never_repeats_paid_post(tmp_path):
    source=tmp_path/'person.png';source.write_bytes(png('navy'))
    reference=tmp_path/'skin.png';reference.write_bytes(png('pink'))
    calls=[]
    def transport(*args):calls.append(1);raise TimeoutError('upstream secret must not be returned')
    client=TwoImageRefinement(lambda:{'api_key':'fake-only','base_url':'http://fixture.invalid/v1'},transport=transport)
    for _ in range(2):
        with pytest.raises(WorkError,match='核对'):client.run(tmp_path/'job',source,reference,'精修')
    assert len(calls)==1
    record=json.loads((tmp_path/'job/operation.json').read_text(encoding='utf-8'))
    assert record['status']=='submission_unknown'
    assert 'secret' not in json.dumps(record)
