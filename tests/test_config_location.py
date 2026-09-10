"""配置位置与便携模式测试。

覆盖：路径解析优先级、旧位置迁移、便携判定、损坏配置容错。
"""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from roller.infrastructure import config_store as cs
from roller.infrastructure.config_store import AppConfig, ConfigStore


def _isolate(monkeypatch_dir: Path):
    """把 app_dir / user_dir 指到临时目录，避免碰真实配置。"""


def test_resolve_uses_override_env(monkeypatch=None):
    """CLASS_ROLLER_CONFIG 环境变量优先级最高。"""
    target = Path(tempfile.mkdtemp()) / "custom.json"
    old = os.environ.get("CLASS_ROLLER_CONFIG")
    os.environ["CLASS_ROLLER_CONFIG"] = str(target)
    try:
        assert cs.resolve_config_path() == target
    finally:
        if old is None:
            os.environ.pop("CLASS_ROLLER_CONFIG", None)
        else:
            os.environ["CLASS_ROLLER_CONFIG"] = old


def test_portable_mode_when_app_dir_writable():
    """程序目录可写时应使用便携配置（与 exe 放一起）。"""
    tmp = Path(tempfile.mkdtemp())
    old_app, old_user = cs.app_dir, cs.user_dir
    cs.app_dir = lambda: tmp / "program"
    cs.user_dir = lambda: tmp / "userdata"
    (tmp / "program").mkdir(parents=True)
    try:
        resolved = cs.resolve_config_path()
        assert resolved == tmp / "program" / cs.CONFIG_FILE_NAME, resolved
    finally:
        cs.app_dir, cs.user_dir = old_app, old_user


def test_fallback_to_user_dir_when_not_writable():
    """程序目录不可写时退回 %APPDATA%。"""
    tmp = Path(tempfile.mkdtemp())
    old_app, old_user = cs.app_dir, cs.user_dir
    old_writable = cs._is_writable

    cs.app_dir = lambda: tmp / "readonly"
    cs.user_dir = lambda: tmp / "userdata"
    cs._is_writable = lambda d: False
    try:
        resolved = cs.resolve_config_path()
        assert resolved == tmp / "userdata" / cs.CONFIG_FILE_NAME, resolved
    finally:
        cs.app_dir, cs.user_dir = old_app, old_user
        cs._is_writable = old_writable


def test_existing_portable_config_wins():
    """便携目录已有配置时直接沿用，不再迁移。"""
    tmp = Path(tempfile.mkdtemp())
    old_app, old_user = cs.app_dir, cs.user_dir
    program = tmp / "program"
    program.mkdir(parents=True)
    (program / cs.CONFIG_FILE_NAME).write_text('{"names":["张三"]}', encoding="utf-8")

    cs.app_dir = lambda: program
    cs.user_dir = lambda: tmp / "userdata"
    try:
        resolved = cs.resolve_config_path()
        assert resolved == program / cs.CONFIG_FILE_NAME
        # 不应被改写成别的内容
        data = json.loads(resolved.read_text(encoding="utf-8"))
        assert data["names"] == ["张三"]
    finally:
        cs.app_dir, cs.user_dir = old_app, old_user


def test_legacy_config_migrated():
    """升级场景：%APPDATA% 里的旧配置应被搬到便携位置。"""
    tmp = Path(tempfile.mkdtemp())
    old_app, old_user = cs.app_dir, cs.user_dir
    program = tmp / "program"
    userdata = tmp / "userdata"
    program.mkdir(parents=True)
    userdata.mkdir(parents=True)

    legacy = userdata / cs.CONFIG_FILE_NAME
    legacy.write_text(
        json.dumps({"names": ["李四", "王五"]}, ensure_ascii=False), encoding="utf-8"
    )

    cs.app_dir = lambda: program
    cs.user_dir = lambda: userdata
    try:
        resolved = cs.resolve_config_path()
        assert resolved == program / cs.CONFIG_FILE_NAME
        assert resolved.exists(), "旧配置应被迁移到便携位置"
        data = json.loads(resolved.read_text(encoding="utf-8"))
        assert data["names"] == ["李四", "王五"]
        # 旧文件应被改名备份，避免下次又迁移一遍
        assert not legacy.exists()
        assert (userdata / "config.migrated.json").exists()
    finally:
        cs.app_dir, cs.user_dir = old_app, old_user


def test_migration_does_not_overwrite_existing():
    """目标已存在时不覆盖，避免丢数据。"""
    tmp = Path(tempfile.mkdtemp())
    old_app, old_user = cs.app_dir, cs.user_dir
    program = tmp / "program"
    userdata = tmp / "userdata"
    program.mkdir(parents=True)
    userdata.mkdir(parents=True)

    (program / cs.CONFIG_FILE_NAME).write_text('{"names":["新的"]}', encoding="utf-8")
    (userdata / cs.CONFIG_FILE_NAME).write_text('{"names":["旧的"]}', encoding="utf-8")

    cs.app_dir = lambda: program
    cs.user_dir = lambda: userdata
    try:
        cs.resolve_config_path()
        data = json.loads((program / cs.CONFIG_FILE_NAME).read_text(encoding="utf-8"))
        assert data["names"] == ["新的"], "不应覆盖已有便携配置"
    finally:
        cs.app_dir, cs.user_dir = old_app, old_user


def test_is_portable_flag():
    """ConfigStore.is_portable 应正确反映配置位置。"""
    tmp = Path(tempfile.mkdtemp())
    old_app = cs.app_dir
    program = tmp / "program"
    program.mkdir(parents=True)
    cs.app_dir = lambda: program
    try:
        store = ConfigStore(program / cs.CONFIG_FILE_NAME)
        assert store.is_portable is True

        store2 = ConfigStore(tmp / "elsewhere" / cs.CONFIG_FILE_NAME)
        assert store2.is_portable is False
    finally:
        cs.app_dir = old_app


def test_config_roundtrip_portable():
    """便携配置读写正常。"""
    path = Path(tempfile.mkdtemp()) / "config.json"
    store = ConfigStore(path)
    cfg = AppConfig()
    cfg.names = ["张三", "李四"]
    cfg.window_width = 520
    store.save(cfg)

    loaded = store.load()
    assert loaded.names == ["张三", "李四"]
    assert loaded.window_width == 520


def test_corrupt_config_falls_back():
    """配置损坏不应导致崩溃。"""
    path = Path(tempfile.mkdtemp()) / "bad.json"
    path.write_text("{{{ 不是 json", encoding="utf-8")
    cfg = ConfigStore(path).load()
    assert cfg.names == []
    assert cfg.always_on_top is True


if __name__ == "__main__":
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except Exception as exc:
                failures.append((name, exc))
                print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
    print()
    if failures:
        print(f"{len(failures)} 个失败")
    else:
        print("全部通过")
    raise SystemExit(1 if failures else 0)
