"""Prepare a complete-sentence 16-second sample from verified local media."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--data',type=Path,required=True);p.add_argument('--ffmpeg',required=True);a=p.parse_args()
    prior=json.loads((a.source/'episode.json').read_bytes());dest=a.data/'public';dest.mkdir(parents=True,exist_ok=True);files={}
    names=['robot.mp4','dog.mp4','children.mp4','store.mp4','host-open.mp4','host-close.mp4','robot.jpg','dog.jpg','children.jpg','store.jpg','font.ttf']
    for name in names:
        row=prior['files'][name]
        if sha(row['path'])!=row['sha256']:raise ValueError('Source changed: '+name)
        path=dest/name;shutil.copyfile(row['path'],path);files[name]={'path':str(path.resolve()),'sha256':sha(path),'source':row}
    mix=prior['sources']['mix.wav']
    if sha(mix['path'])!=mix['sha256']:raise ValueError('Original audio identity changed')
    subprocess.run([a.ffmpeg,'-v','error','-y','-i',mix['path'],'-af','atrim=start=14.8:end=30.8,asetpts=PTS-STARTPTS','-c:a','pcm_s16le',str(dest/'sample.wav')],check=True,creationflags=0x08000000)
    files['sample.wav']={'path':str((dest/'sample.wav').resolve()),'sha256':sha(dest/'sample.wav'),'source':mix,'range':[14.8,30.8]}
    episode={'contract':'kinetic-field-assets-v1','paid_calls':0,'files':files,'sync':{'audio_source':[14.8,30.8],'host-close':{'output':[8,12],'original':[22.8,26.8]},'host-open':{'output':[12,16],'original':[26.8,30.8]}},'rights':'User-authorized local media; private test, no redistribution.'}
    (a.data/'episode.json').write_text(json.dumps(episode,ensure_ascii=False,indent=2),encoding='utf-8');print('Local sample prepared; 16 seconds; no provider calls.')
if __name__=='__main__':main()
