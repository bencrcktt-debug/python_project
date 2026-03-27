from __future__ import annotations

from pathlib import Path

from tfl_app.config import paths


def test_reference_snapshot_dir_defaults_to_root_data_folder() -> None:
    assert paths.REFERENCE_SNAPSHOT_DIR == Path(paths.REPO_ROOT) / "data" / "reference_snapshots"


def test_resolve_data_path_prefers_repo_data_folder(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(paths, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "data")
    monkeypatch.delenv("DATA_PATH", raising=False)

    dataset_dir = paths.DATA_DIR / paths.DEFAULT_DATA_FILENAME
    dataset_dir.parent.mkdir(parents=True, exist_ok=True)
    dataset_dir.mkdir()

    assert paths.resolve_data_path() == str(dataset_dir)
