"""Loopback-only audition player with byte-range support."""
import argparse
from pathlib import Path
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
p=argparse.ArgumentParser();p.add_argument('--directory',required=True);p.add_argument('--port',type=int,default=14877);a=p.parse_args()
app=Starlette(routes=[Mount('/',app=StaticFiles(directory=Path(a.directory).resolve(),html=True))])
uvicorn.run(app,host='127.0.0.1',port=a.port)
