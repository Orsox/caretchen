import json
import time
from pathlib import Path

from dictapaste.history import DictationHistory, HistoryEntry


def test_add_and_retrieve(tmp_path):
    history_path = tmp_path / "history.json"
    history = DictationHistory(history_path)

    history.add("raw text", "refined text", True)
    history.add("another raw", "another refined", False)

    entries = history.entries
    assert len(entries) == 2
    assert entries[0].raw_text == "raw text"
    assert entries[0].refined_text == "refined text"
    assert entries[0].was_refined is True
    assert entries[1].raw_text == "another raw"
    assert entries[1].was_refined is False


def test_count(tmp_path):
    history_path = tmp_path / "history.json"
    history = DictationHistory(history_path)

    assert history.count == 0
    history.add("a", "b", False)
    assert history.count == 1


def test_persistence(tmp_path):
    history_path = tmp_path / "history.json"
    history = DictationHistory(history_path)
    history.add("persisted", "yes", True)

    # Reload from disk
    history2 = DictationHistory(history_path)
    assert len(history2.entries) == 1
    assert history2.entries[0].raw_text == "persisted"


def test_clear(tmp_path):
    history_path = tmp_path / "history.json"
    history = DictationHistory(history_path)
    history.add("a", "b", False)
    history.add("c", "d", True)
    history.clear()

    assert history.count == 0
    assert history.entries == []


def test_max_entries(tmp_path):
    history_path = tmp_path / "history.json"
    history = DictationHistory(history_path)
    history._max_entries = 3

    for i in range(5):
        history.add(f"entry {i}", f"refined {i}", False)

    assert len(history.entries) == 3
    assert history.entries[0].raw_text == "entry 2"
    assert history.entries[2].raw_text == "entry 4"


def test_iso_timestamp(tmp_path):
    history_path = tmp_path / "history.json"
    history = DictationHistory(history_path)
    history.add("raw", "refined", True)

    entry = history.entries[0]
    # Should be a valid ISO format
    assert "T" in entry.timestamp
    assert entry.timestamp.endswith("+00:00")


def test_save_and_load_json_format(tmp_path):
    history_path = tmp_path / "history.json"
    history = DictationHistory(history_path)
    history.add("test", "refined", True)

    data = json.loads(history_path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["raw_text"] == "test"
    assert data[0]["refined_text"] == "refined"
    assert data[0]["was_refined"] is True


def test_thread_safety(tmp_path):
    import threading

    history_path = tmp_path / "history.json"
    history = DictationHistory(history_path)

    def add_entries(start, count):
        for i in range(count):
            history.add(f"thread entry {start + i}", f"refined {start + i}", False)

    threads = [threading.Thread(target=add_entries, args=(i * 10, 10)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert history.count == 30
