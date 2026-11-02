"""Each supported helper keeps an independent pin and old releases keep theirs."""
import pytest
import hashlib
import json

from backlot import studio_motiongit as motion
from backlot.work_catalog import WorkError


def test_existing_helper_pin_is_unchanged():
    assert motion.helper_identity()['version'] == '1.0.0-rc.50'
    assert motion.helper_identity()['sha256'] == motion.HELPER_SHA


def test_chalkboard_helper_is_exactly_pinned():
    pin = motion.helper_identity({'helper_version': '1.0.0-rc.51'})
    assert pin['sha256'] == '2748865645a5a0911de4ca79a4186c7ee5f1c7157e09eb72904bd2330463304b'
    assert pin['bytes'] == 842265
    assert pin['metadata_url'].endswith('/1.0.0-rc.51.json')


def test_package_cannot_select_an_unreviewed_helper():
    with pytest.raises(WorkError):
        motion.helper_identity({'helper_version': '1.0.0-rc.52'})


def test_registry_move_never_rebinds_new_package_to_old_helper(tmp_path, monkeypatch):
    monkeypatch.setattr(motion, 'STORE', tmp_path)
    old = tmp_path / 'tools' / motion.HELPER_VERSION / 'motion.mjs'
    old.parent.mkdir(parents=True)
    old.write_bytes(b'old-helper')
    monkeypatch.setattr(motion, 'HELPER_SHA', hashlib.sha256(b'old-helper').hexdigest())
    value = {'id': 'mg-future', 'helper_version': '1.0.0-rc.51',
             'helper': 'X:/previous-installation/rc51/motion.mjs'}
    motion._put_package(value)
    assert motion._get('packages', value['id'])['helper'] == value['helper']
