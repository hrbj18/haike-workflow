"""Relocate explicitly bundled private template inputs without downloading files."""
import hashlib
import json
from pathlib import Path
import os
import tempfile

MANIFEST='.local/motion-console/portable-assets.json'
MANIFESTS=(MANIFEST,'.local/motion-native-story/portable-assets.json','.local/motion-poster/portable-assets.json')


def encoded(value):
    return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8')


def materialize(root):
    root=Path(root).resolve()
    def safe(raw):
        path=Path(raw)
        if not path.is_absolute():path=root/path
        path=Path(os.path.abspath(path))
        if not path.is_relative_to(root):raise ValueError('模板资产路径越过安装目录')
        for part in [path,*path.parents]:
            if part==root.parent:break
            if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):
                raise ValueError('模板资产不能通过目录链接定位')
        return path
    documents={}
    for name in MANIFESTS:
        manifest=safe(name)
        if not manifest.is_file():continue
        plan=json.loads(manifest.read_text(encoding='utf-8'))
        if plan.get('schema')!=1 or not isinstance(plan.get('documents'),dict):
            raise ValueError('模板迁移清单无效')
        for name,value in plan['documents'].items():
            path=safe(name)
            if not path.is_relative_to(manifest.parent/'assets') or path.suffix!='.json' or path in documents:
                raise ValueError('模板迁移只能生成自有输入文档')
            if not isinstance(value,str):raise ValueError('模板迁移文档必须保留原始 UTF-8 文本')
            json.loads(value)
            documents[path]=value
    generated={};active=set()
    def build(path):
        if path in generated:return generated[path]
        if path in active:raise ValueError('模板输入存在循环引用')
        active.add(path)
        def walk(value):
            if isinstance(value,list):return [walk(x) for x in value]
            if not isinstance(value,dict):return value
            result={k:walk(v) for k,v in value.items()}
            if isinstance(value.get('path'),str) and 'sha256' in value:
                target=safe(path.parent/value['path'])
                if target in documents:
                    if hashlib.sha256(documents[target].encode('utf-8')).hexdigest()!=value['sha256']:
                        raise ValueError('模板输入文档身份不一致')
                    data=build(target);digest=hashlib.sha256(data).hexdigest()
                else:
                    if not target.is_file():raise ValueError('模板输入文件缺失：'+target.name)
                    with target.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
                    if digest!=value['sha256']:raise ValueError('模板输入文件校验失败：'+target.name)
                result.update(path=str(target),sha256=digest)
            return result
        data=encoded(walk(json.loads(documents[path])));generated[path]=data;active.remove(path);return data
    # Validate the entire dependency graph before changing any generated input.
    for path in documents:build(path)
    changed=0
    for path,data in generated.items():
        if path.is_file() and path.read_bytes()==data:continue
        path.parent.mkdir(parents=True,exist_ok=True)
        fd,temp=tempfile.mkstemp(prefix='.relocate-',dir=path.parent)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(data)
            os.replace(temp,path);changed+=1
        finally:Path(temp).unlink(missing_ok=True)
    return changed
