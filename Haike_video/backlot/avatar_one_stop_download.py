"""Verified range downloads of an existing HQ object through Windows Schannel."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import math
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import unquote,urlsplit

from backlot.studio import atomic_private
from backlot.work_catalog import WorkError


def windows_artifact(executor, row, target, case, task_id):
    """Return False when unavailable; no keys, generation, or TLS exceptions."""
    cache = case/'outputs-legacy.json'
    curl = Path(os.environ.get('SystemRoot', 'C:/Windows'))/'System32/curl.exe'
    if os.name != 'nt' or not curl.is_file() or not cache.is_file() or not hasattr(executor,'matching_artifact_url'):
        return False
    import json
    legacy = json.loads(cache.read_text('utf-8'))
    if str(legacy.get('task_id')) != str(task_id):
        return False
    rows = (legacy.get('response') or {}).get('data') or []
    selected = executor.matching_artifact_url(row, rows if isinstance(rows,list) else [])
    a,b = urlsplit(row['url']),urlsplit(selected)
    if selected == row['url'] or b.scheme != 'https' or not b.hostname or unquote(a.path) != unquote(b.path):
        return False
    download_ranges(curl,selected,target)
    atomic_private(target.with_name(target.name+'.download.json'),{
        'task_id':str(task_id),'node_id':str(row['nodeId']),'same_storage_object_path':True,
        'original_url_sha256':hashlib.sha256(row['url'].encode()).hexdigest(),
        'selected_url_sha256':hashlib.sha256(selected.encode()).hexdigest(),
        'sha256':file_sha(target),'tls_verification':True,'new_generation':False,
        'transport':'Windows system curl; verified byte ranges'})
    return True


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def download_ranges(curl,url,target):
    if urlsplit(url).scheme != 'https':
        raise WorkError('成品恢复只接受原任务HTTPS对象')
    target = Path(target)
    url_sha = hashlib.sha256(url.encode()).hexdigest()
    parts = target.with_name(target.name+'.schannel-'+url_sha[:12])
    parts.mkdir(parents=True,exist_ok=True)
    block = 1024*1024

    def fetch(index,total=None):
        start = index*block
        end = start+block-1 if total is None else min(total-1,start+block-1)
        path = parts/f'{index:08d}'
        if total is not None and path.is_file() and path.stat().st_size == end-start+1:
            return path,total,False
        temporary,headers = path.with_suffix('.partial'),path.with_suffix('.headers')
        for attempt in range(3):
            try:
                response = subprocess.run([str(curl),'--silent','--show-error','--fail',
                    '--connect-timeout','8','--max-time','30','--max-filesize','2000000000',
                    '--range',f'{start}-{end}','--dump-header',str(headers),
                    '--output',str(temporary),'--write-out','%{http_code}',url],
                    capture_output=True,timeout=35,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                status = response.stdout.strip()
                if response.returncode or status not in {b'200',b'206'} or not temporary.is_file():
                    raise WorkError('原任务成品下载暂未完成，保留分块和原编号，仅恢复下载')
                text = headers.read_text('latin-1')
                size = temporary.stat().st_size
                if status == b'200':
                    lengths = re.findall(r'(?im)^content-length:\s*(\d+)\s*$',text)
                    if start != 0 or not 0 < size < 2_000_000_000 or lengths and size != int(lengths[-1]):
                        raise WorkError('原任务成品响应长度异常，保留原任务')
                    temporary.replace(path)
                    return path,size,True
                ranges = re.findall(r'(?im)^content-range:\s*bytes (\d+)-(\d+)/(\d+)\s*$',text)
                if not ranges:
                    raise WorkError('原任务成品缺少字节范围回执')
                first,last,actual_total = map(int,ranges[-1])
                if (not 0 < actual_total < 2_000_000_000 or first != start
                        or last != min(end,actual_total-1) or size != last-first+1
                        or total is not None and total != actual_total):
                    raise WorkError('原任务成品字节范围不符，保留分块，未采用不完整文件')
                temporary.replace(path)
                return path,actual_total,False
            except (subprocess.SubprocessError,OSError,WorkError):
                if attempt == 2:
                    raise WorkError('原任务成品下载未完成，已保留分块、证书验证与原任务，未重新生成') from None
                time.sleep(attempt+1)

    first,total,whole = fetch(0)
    atomic_private(parts/'identity.json',{'url_sha256':url_sha,'bytes':total,'tls_verification':True})
    if whole:
        first.replace(target)
        return
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda index:fetch(index,total),range(1,math.ceil(total/block))))
    temporary = target.with_name(target.name+'.assembling')
    with temporary.open('wb') as output:
        for index in range(math.ceil(total/block)):
            with (parts/f'{index:08d}').open('rb') as source:
                while chunk := source.read(block):
                    output.write(chunk)
    if temporary.stat().st_size != total:
        raise WorkError('原任务成品合并长度不符')
    temporary.replace(target)
