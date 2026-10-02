from __future__ import annotations

from clipflow.single_instance import SingleInstance, instance_key


def test_second_instance_hands_off_to_first(qapp, qtbot, tmp_path):
    key = instance_key(str(tmp_path))
    primary = SingleInstance(key)
    assert primary.acquire()
    try:
        with qtbot.waitSignal(primary.activation_requested, timeout=2000):
            assert not SingleInstance(key).acquire()
    finally:
        primary.release()


def test_keys_differ_per_data_dir(tmp_path):
    assert instance_key(str(tmp_path / "a")) != instance_key(str(tmp_path / "b"))
