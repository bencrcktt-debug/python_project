from __future__ import annotations

import tempfile
import uuid

import _pytest.pathlib
import _pytest.tmpdir


_ORIGINAL_CLEANUP_DEAD_SYMLINKS = _pytest.pathlib.cleanup_dead_symlinks
_ORIGINAL_FIND_PREFIXED = _pytest.pathlib.find_prefixed
_ORIGINAL_GETBASETEMP = _pytest.tmpdir.TempPathFactory.getbasetemp
_ORIGINAL_MKTEMP = _pytest.tmpdir.TempPathFactory.mktemp


def _safe_cleanup_dead_symlinks(root) -> None:
    try:
        _ORIGINAL_CLEANUP_DEAD_SYMLINKS(root)
    except PermissionError:
        # The workspace sandbox can leave pytest's temp root unreadable at session finish.
        return


def _safe_find_prefixed(root, prefix):
    try:
        yield from _ORIGINAL_FIND_PREFIXED(root, prefix)
    except PermissionError:
        # The same sandbox quirk can block directory scans for tmp_path numbering.
        return


def _safe_getbasetemp(self):
    if self._basetemp is not None:
        return self._basetemp
    if self._given_basetemp is not None:
        candidate = _pytest.pathlib.Path(tempfile.gettempdir()) / f"{self._given_basetemp.name}-{uuid.uuid4().hex}"
        candidate.mkdir()
        self._basetemp = candidate.resolve()
        return self._basetemp
    return _ORIGINAL_GETBASETEMP(self)


def _safe_mktemp(self, basename, numbered=True):
    relative_name = str(self._ensure_relative_to_basetemp(basename)).replace("\\", "-").replace("/", "-")
    root = self.getbasetemp()
    if not numbered:
        target = root / relative_name
        target.mkdir()
        return target

    target = root / f"{relative_name}-{uuid.uuid4().hex}"
    target.mkdir()
    self._trace("mktemp", target)
    return target


_pytest.pathlib.find_prefixed = _safe_find_prefixed
_pytest.pathlib.cleanup_dead_symlinks = _safe_cleanup_dead_symlinks
_pytest.tmpdir.cleanup_dead_symlinks = _safe_cleanup_dead_symlinks
_pytest.tmpdir.TempPathFactory.getbasetemp = _safe_getbasetemp
_pytest.tmpdir.TempPathFactory.mktemp = _safe_mktemp
