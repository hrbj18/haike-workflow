"""Prepare new private episode inputs without editing the approved template."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
CONTRACT=json.loads((HERE/'input-contract.json').read_bytes())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def validate(request, probe):
    if set(request)!={'contract','content','files','avatar_sync','rights'} or request['contract']!=CONTRACT['contract']:
        raise ValueError('请使用 kinetic-field-request-v1 的固定字段')
    if not isinstance(request['rights'],str) or not request['rights'].strip():raise ValueError('缺少本期素材使用权说明')
    if not isinstance(request['content'],dict) or set(request['content'])!=set(CONTRACT['text_limits']):raise ValueError('新一期必须填写全部13个短文字槽，不沿用示例地址')
    for key,limit in CONTRACT['text_limits'].items():
        value=request['content'][key]
        if not isinstance(value,str) or not value.strip() or re.search(r'[\n\r。！？<>]',value):raise ValueError('文字槽只允许非空短标签: '+key)
        if sum(.55 if ord(c)<128 else 1 for c in value)>limit:raise ValueError('请精简过长标签: '+key)
    expected_sync={'host-close.mp4':[8,12],'host-open.mp4':[12,16]}
    if request['avatar_sync']!=expected_sync:raise ValueError('人物片段必须对应本期音轨8–12秒和12–16秒；不拉伸或循环')
    if not isinstance(request['files'],dict) or set(request['files'])!=set(CONTRACT['files']):raise ValueError('缺少素材、声音或字体槽')
    result={}
    for name,rule in CONTRACT['files'].items():
        row=request['files'][name]
        if not isinstance(row,dict) or set(row)!={'path','sha256','provenance'}:raise ValueError('素材需绝对路径、SHA256与来源: '+name)
        path=Path(row['path'])
        if not path.is_absolute() or not path.is_file() or not row['provenance']:raise ValueError('素材路径或来源无效: '+name)
        if path.suffix.lower()!=Path(name).suffix:raise ValueError('素材扩展名与槽不一致: '+name)
        if sha(path)!=row['sha256']:raise ValueError('素材身份变化: '+name)
        if rule['kind']!='font':
            info=probe(path);kind='audio' if rule['kind']=='audio' else 'video'
            streams=[s for s in info.get('streams',[]) if s.get('codec_type')==kind]
            if not streams:raise ValueError('素材流类型错误: '+name)
            if rule['kind']!='image':
                duration=float(streams[0].get('duration',info.get('format',{}).get('duration',0)))
                if not math.isfinite(duration):raise ValueError('素材时长无效: '+name)
                if rule['kind']=='audio' and abs(duration-16)>1/24:raise ValueError('当前版本支持16秒完整语意声音；更长口播需独立改编')
                minimum=rule.get('min_seconds',0)
                accepted=rule.get('approved_tail_hold',{})
                if row['sha256']==accepted.get('sha256'):minimum=accepted['min_seconds']
                if duration<minimum:raise ValueError('素材不足，不自动循环或冻结补时: '+name)
        result[name]=row
    return result

def prepare(request, data, probe):
    rows=validate(request,probe)
    if data.exists() and any(data.iterdir()):raise ValueError('目标已有任务；先读取原episode和队列，不覆盖')
    public=data/'public';public.mkdir(parents=True,exist_ok=True);files={}
    for name,row in rows.items():
        path=public/name;shutil.copyfile(row['path'],path)
        if sha(path)!=row['sha256']:raise ValueError('复制期间素材变化，保留目录供检查: '+name)
        files[name]={'path':str(path.resolve()),'sha256':row['sha256'],'source':row}
    episode={'contract':'kinetic-field-assets-v1','template_id':'kinetic-field-v1','template_version':'1.0.0','content':request['content'],'files':files,'sync':request['avatar_sync'],'rights':request['rights'],'paid_calls':0}
    (data/'episode.json').write_text(json.dumps(episode,ensure_ascii=False,indent=2),encoding='utf-8')
    return episode

def main():
    p=argparse.ArgumentParser();p.add_argument('--request',type=Path,required=True);p.add_argument('--data',type=Path,required=True);p.add_argument('--ffprobe',required=True);a=p.parse_args()
    def probe(path):return json.loads(subprocess.check_output([a.ffprobe,'-v','error','-show_streams','-show_format','-of','json',str(path)],creationflags=0x08000000))
    prepare(json.loads(a.request.read_bytes()),a.data.resolve(),probe)
    print('动效模板2本期输入已准备；模板画面/动效未改动；没有新增付费调用。')
if __name__=='__main__':main()
