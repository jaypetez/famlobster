import os
import stat
import sys

import pytest

from famlobster._fs import write_private

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")


def _mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def test_write_private_writes_content_and_creates_dirs(tmp_path):
    path = tmp_path / "nested" / "token.json"
    write_private(path, '{"a": 1}')
    assert path.read_text() == '{"a": 1}'


@posix_only
def test_write_private_new_file_is_owner_only(tmp_path):
    path = tmp_path / "token.json"
    write_private(path, "secret")
    assert _mode(path) == 0o600


@posix_only
def test_write_private_tightens_existing_file(tmp_path):
    path = tmp_path / "token.json"
    path.write_text("old")
    os.chmod(path, 0o644)
    write_private(path, "new")
    assert path.read_text() == "new"
    assert _mode(path) == 0o600


@posix_only
def test_reminders_file_is_owner_only(tmp_reminders_file):
    from famlobster.reminders import _write_reminders_file

    _write_reminders_file([])
    assert _mode(tmp_reminders_file) == 0o600
