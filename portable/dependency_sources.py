"""Process-local dependency sources shared by setup, builds and source updates."""
from __future__ import annotations

import os
from urllib.parse import urlsplit

PIP_INDEX = 'https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple'
NPM_REGISTRY = 'https://registry.npmmirror.com'
PYTHON_MIRROR = NPM_REGISTRY + '/-/binary/python-build-standalone'


def public_https(value):
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('依赖镜像必须是无凭据的 HTTPS 地址')
    return value.rstrip('/')


def environment(base=None):
    """Do not mutate the user's global pip/npm configuration or export Keys."""
    env = dict(os.environ if base is None else base)
    pip = public_https(env.get('HAIKE_PIP_INDEX_URL') or PIP_INDEX)
    npm = public_https(env.get('HAIKE_NPM_REGISTRY') or NPM_REGISTRY)
    for key in list(env):
        if key.upper() in {'PIP_EXTRA_INDEX_URL', 'UV_EXTRA_INDEX_URL', 'UV_INDEX', 'UV_INDEX_URL',
                           'UV_DEFAULT_INDEX', 'NPM_CONFIG_REGISTRY', 'PIP_NO_INDEX', 'UV_OFFLINE',
                           'NPM_CONFIG_OFFLINE', 'HAIKE_PORTABLE_OFFLINE', 'UV_PYTHON_DOWNLOADS'}:
            env.pop(key)
    env.update(PIP_INDEX_URL=pip, PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK='1',
               UV_DEFAULT_INDEX=pip, UV_INDEX_URL=pip, UV_NO_CONFIG='1',
               UV_PYTHON_INSTALL_MIRROR=PYTHON_MIRROR,
               npm_config_registry=npm, npm_config_audit='false', npm_config_fund='false',
               PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD='1', PUPPETEER_SKIP_DOWNLOAD='true',
               PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    return env
