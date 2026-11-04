"""Read-only verification of a locally built candidate and its actual inputs."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def verify(directory):
    directory=Path(directory).resolve()
    manifest=json.loads((directory/'build-manifest.json').read_text('utf-8'))
    count=0
    for group in ('sources','inputs','assets','outputs'):
        for item in manifest[group]:
            if item.get('virtual'):continue
            file=Path(item['path']) if group in ('sources','inputs') else directory/item['path']
            if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest()!=item['sha256']:
                raise ValueError(f'{group} identity changed: {file}')
            count+=1
    composer=Path(__file__).resolve().parents[2]/'remotion-composer'
    code="const r=require('module').createRequire(process.cwd()+'/package.json');process.stdout.write(JSON.stringify(Object.fromEntries("+json.dumps(list(manifest['dependencies']))+".map(n=>[n,require(r.resolve(n+'/package.json')).version]))))"
    current=json.loads(subprocess.check_output(['node','-e',code],cwd=composer,text=True))
    if current!=manifest['dependencies']:raise ValueError('installed dependency versions changed')
    return {'valid':True,'checked':count,'templateId':manifest['templateId'],'version':manifest['version']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path)
    print(json.dumps(verify(p.parse_args().directory),ensure_ascii=False))
