"""Inspect pinned existing JSON-schema dependencies; never install or copy them."""
from concurrent.futures import ThreadPoolExecutor
import importlib.metadata
import importlib.util
from pathlib import Path
import re

try:
    from . import app_update as core
except ImportError:
    try: import release_core as core
    except ImportError:
        spec=importlib.util.spec_from_file_location('schema_runtime_core',Path(__file__).with_name('app_update.py'))
        core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)

PATH='Haike_video/templates/motion-presets/schema-runtime.json'
SCHEMA='haike.schema-runtime/1'
BASE='Haike_video/.venv/Lib/site-packages/'
DISTRIBUTIONS=('attrs','jsonschema','jsonschema-specifications','referencing','rpds-py','typing-extensions')
PACKAGES={'attr','attrs','jsonschema','jsonschema_specifications','referencing','rpds','typing_extensions.py'}
DIST_NAMES={'attrs','jsonschema','jsonschema_specifications','referencing','rpds_py','typing_extensions'}


def require(ok,message):
    if not ok: raise core.UpdateError(message)


def public_resource(name):
    core._parts(name)
    if not name.startswith(BASE): return False
    first=name[len(BASE):].split('/')[0]
    return first in PACKAGES or any(re.fullmatch(re.escape(d)+r'-[0-9][0-9A-Za-z.+-]*\.dist-info',first) for d in DIST_NAMES)


def build(site_packages):
    root=Path(site_packages).resolve(strict=True)
    distributions={d.metadata['Name'].lower().replace('_','-'):d
                   for d in importlib.metadata.distributions(path=[str(root)])}
    names=set();versions={}
    for name in DISTRIBUTIONS:
        require(name in distributions,'离线JSONschema依赖缺失：'+name)
        distribution=distributions[name];versions[name]=distribution.version
        for relative in distribution.files or []:
            relative=relative.as_posix()
            if relative.startswith('../') or '__pycache__' in relative.split('/') or relative.endswith(('.pyc','.pyo')):continue
            target=BASE+relative
            if public_resource(target):names.add(relative)
    require(names,'JSONschema依赖清单为空')
    rows=[]
    for name in sorted(names):
        file=core.safe_path(root,name)
        require(file.is_file(),'JSONschema分发文件缺失：'+name)
        rows.append((BASE+name,file))
    value={'schema':SCHEMA,'python_abi':'cp312-win_amd64','distributions':versions,
           'files':{name:core.digest(file) for name,file in rows}}
    return value,rows


def verify(root,value=None):
    path=core.safe_path(root,PATH)
    if value is None and not path.is_file():return {'status':'not-declared'}
    value=core._read(path) if value is None else value
    require(value.get('schema')==SCHEMA and value.get('python_abi')=='cp312-win_amd64'
            and set(value.get('distributions',{}))==set(DISTRIBUTIONS)
            and isinstance(value.get('files'),dict) and 1<=len(value['files'])<=2000,'JSONschema运行依赖身份无效')
    def check(item):
        name,digest=item
        require(public_resource(name) and isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest),
                'JSONschema运行依赖路径无效')
        path=core.safe_path(root,name)
        require(path.is_file() and core.digest(path)==digest,'JSONschema运行依赖缺失或改变：'+name)
    with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(check,value['files'].items()))
    return {'status':'verified','files':len(value['files']),'distributions':value['distributions']}
