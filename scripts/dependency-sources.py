"""Return only public dependency settings for the PowerShell setup entry."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portable.dependency_sources import environment

KEYS = ('PIP_INDEX_URL', 'PIP_CONFIG_FILE', 'PIP_DISABLE_PIP_VERSION_CHECK', 'UV_DEFAULT_INDEX',
        'UV_INDEX_URL', 'UV_NO_CONFIG', 'UV_PYTHON_INSTALL_MIRROR', 'npm_config_registry',
        'npm_config_audit', 'npm_config_fund', 'PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD',
        'PUPPETEER_SKIP_DOWNLOAD', 'PYTHONUTF8', 'PYTHONIOENCODING')

if __name__ == '__main__':
    values = environment()
    settings = {key: values[key] for key in KEYS}
    settings.update({key: None for key in ('PIP_EXTRA_INDEX_URL', 'UV_EXTRA_INDEX_URL', 'UV_INDEX',
                                          'PIP_NO_INDEX', 'UV_OFFLINE', 'NPM_CONFIG_OFFLINE',
                                          'HAIKE_PORTABLE_OFFLINE', 'UV_PYTHON_DOWNLOADS')})
    print(json.dumps(settings))
