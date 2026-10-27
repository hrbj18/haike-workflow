"""python -m image_refinement --host 127.0.0.1 --port 4765"""

import argparse
import os

from .api import create_app


def main():
    parser = argparse.ArgumentParser(description="共享图片精修服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4765)
    args = parser.parse_args()
    if not os.getenv("IMAGE_REFINEMENT_SERVICE_TOKEN"):
        parser.error("请先设置 IMAGE_REFINEMENT_SERVICE_TOKEN；服务不会无鉴权启动。")
    import uvicorn

    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
