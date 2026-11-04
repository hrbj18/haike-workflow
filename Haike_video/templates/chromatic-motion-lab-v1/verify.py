"""Read back a frozen preview: content/assets, source, dependencies and bundle SHA."""
import argparse
import json
from pathlib import Path
from prepare import HERE, require, sha


def verify(output):
    manifest=json.loads((output/'build-manifest.json').read_text('utf-8'))
    preparation=json.loads((output/'preparation.json').read_text('utf-8'))
    require(manifest['schema']=='haike.chromatic-preview/2','不支持的构建清单')
    require(sha(output/'preparation.json')==manifest['preparationSha256'],'准备清单已改变')
    require(sha(HERE/'recipes.json')==preparation['recipeSha256'],'配方已改变，需要重新准备')
    count=0
    def check(path,expected):
        nonlocal count
        require(path.is_file() and sha(path)==expected,'身份不匹配：'+str(path))
        count+=1
    for record in preparation['files']+manifest['outputs']+manifest.get('sampleFiles',[]):
        path=(output/record['path']).resolve()
        require(path.is_relative_to(output.resolve()),'输出清单路径越界')
        check(path,record['sha256'])
    for record in manifest['toolSources']:
        check(HERE/record['path'],record['sha256'])
    working=Path(manifest['workingDirectory'])
    for record in manifest['inputs']:
        if not record.get('virtual'):
            check(working/record['path'],record['sha256'])
    dependency_root=HERE.parents[1]/'remotion-composer/node_modules'
    for name,version in manifest['dependencies'].items():
        actual=json.loads((dependency_root/name/'package.json').read_text('utf-8'))['version']
        require(actual==version,'依赖版本已改变：'+name)
    return {'valid':True,'checkedFiles':count,'recipeRevision':manifest['recipeRevision'],'dependencies':manifest['dependencies'],'scope':'frozen local preview identity; visual/audio/mobile validation separate'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(verify(args.data),ensure_ascii=False))
    except (OSError,KeyError,ValueError) as exc:parser.exit(1,str(exc)+'\n')
