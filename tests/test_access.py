"""Owner access (ADMIN_PASSWORD) and per-visitor visibility of reports / analyses."""

from __future__ import annotations

import pytest

from weather_agent import access, reports, tools, vector_store

GOOD = "test-owner-pass-123"  # test value only


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", GOOD)
    access.reset_throttle()
    yield
    access.reset_throttle()


# ---------------------------------------------------------------- password unlock
def test_owner_mode_needs_a_long_enough_password(monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD")
    assert access.owner_mode_status()[0] is False
    monkeypatch.setenv("ADMIN_PASSWORD", "short")
    ok, reason = access.owner_mode_status()
    assert not ok and "at least" in reason
    ss: dict = {}
    assert access.try_unlock("short", ss)[0] is False and not ss.get("is_owner")


def test_correct_password_unlocks_and_is_not_stored():
    ss: dict = {}
    ok, _ = access.try_unlock(GOOD, ss)
    assert ok and ss["is_owner"] is True
    assert GOOD not in [str(v) for v in ss.values()]
    access.lock(ss)
    assert ss["is_owner"] is False


@pytest.mark.parametrize("guess", ["", "wrong", GOOD[:-1], GOOD + " ", GOOD.upper()])
def test_wrong_passwords_are_rejected(guess):
    ss: dict = {}
    ok, msg = access.try_unlock(guess, ss)
    assert not ok and not ss.get("is_owner") and "Wrong password" in msg


def test_session_is_paused_after_repeated_wrong_guesses():
    ss: dict = {}
    for _ in range(access.SESSION_MAX_FAILS):
        assert access.try_unlock("nope", ss, now=100.0)[0] is False
    ok, msg = access.try_unlock(GOOD, ss, now=101.0)  # even the right password waits out the pause
    assert not ok and "Try again" in msg and not ss.get("is_owner")
    assert access.try_unlock(GOOD, ss, now=100.0 + access.SESSION_LOCK_S + 1)[0] is True


def test_global_throttle_across_sessions():
    for i in range(access.GLOBAL_MAX_FAILS):
        access.try_unlock("nope", {}, now=1000.0 + i)  # many fresh sessions guessing
    ok, msg = access.try_unlock(GOOD, {}, now=1000.0 + access.GLOBAL_MAX_FAILS)
    assert not ok and "paused" in msg
    later = 1000.0 + access.GLOBAL_MAX_FAILS + access.GLOBAL_WINDOW_S + 1
    assert access.try_unlock(GOOD, {}, now=later)[0] is True


# ---------------------------------------------------------------- report library visibility
def _make(snapshot, tmp_path, name, owner):
    return reports.build_pdf(snapshot, name, "text", out_dir=tmp_path, owner=owner).name


def test_visitors_only_see_their_own_reports_owner_sees_all(snapshot, tmp_path):
    mine = _make(snapshot, tmp_path, "Mine", "visitor-a")
    theirs = _make(snapshot, tmp_path, "Theirs", "visitor-b")
    legacy = _make(snapshot, tmp_path, "Old Untagged", "")
    files = lambda entries: {e["file"] for e in entries}  # noqa: E731
    assert files(reports.visible_index("visitor-a", out_dir=tmp_path)) == {mine}
    assert files(reports.visible_index("visitor-b", out_dir=tmp_path)) == {theirs}
    assert reports.visible_index("", out_dir=tmp_path) == []  # no identity -> nothing
    assert files(reports.visible_index("x", see_all=True, out_dir=tmp_path)) == {mine, theirs, legacy}


def test_pdfs_without_index_entry_are_owner_only(tmp_path):
    (tmp_path / "orphan_20260101-000000.pdf").write_bytes(b"%PDF-1.4")
    assert reports.visible_index("visitor-a", out_dir=tmp_path) == []
    assert len(reports.visible_index("", see_all=True, out_dir=tmp_path)) == 1


# ---------------------------------------------------------------- vector archive visibility
def test_search_filter_scopes_to_visitor():
    assert vector_store.search_filter(None, "v1", False) == {"owner": "v1"}
    assert vector_store.search_filter("Lahore", "v1", False) == {"$and": [{"owner": "v1"}, {"city": "Lahore"}]}
    assert vector_store.search_filter(None, "v1", True) is None
    assert vector_store.search_filter("Lahore", "", True) == {"city": "Lahore"}


def test_search_without_identity_returns_nothing(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("store must not be queried")

    monkeypatch.setattr(vector_store, "get_store", boom)
    assert vector_store.search("storm") == []
    assert vector_store.search("storm", owner="") == []


class _FakeStore:
    def __init__(self):
        self.added: list[dict] = []
        self.kwargs: dict = {}

    def add_texts(self, texts, metadatas):
        self.added += metadatas
        return ["id-1"]

    def similarity_search_with_relevance_scores(self, query, **kwargs):
        self.kwargs = kwargs
        return []


def test_analyses_are_tagged_and_extra_cannot_overwrite_owner(monkeypatch):
    store = _FakeStore()
    monkeypatch.setattr(vector_store, "get_store", lambda api_key=None: store)
    vector_store.add_analysis("A", "Lahore", "t", "a.pdf", "Low", {"owner": "attacker", "country": "PK"}, owner="v1")
    assert store.added[0]["owner"] == "v1" and store.added[0]["country"] == "PK"
    vector_store.search("storm", owner="v1")
    assert store.kwargs["filter"] == {"owner": "v1"}


def test_agent_tools_are_bound_to_the_visitor(monkeypatch):
    seen: dict = {}

    def fake_search(query, k=4, city=None, api_key=None, owner="", see_all=False):
        seen.update(owner=owner, see_all=see_all)
        return []

    monkeypatch.setattr(vector_store, "search", fake_search)
    by_name = {t.name: t for t in tools.all_tools(owner="visitor-a")}
    by_name["search_past_analyses"].invoke({"query": "storm"})
    assert seen == {"owner": "visitor-a", "see_all": False}
    # the model can only pass query/city/k: it cannot ask for another visitor's data
    assert set(by_name["search_past_analyses"].args) == {"query", "city", "k"}
    assert "owner" not in by_name["save_analysis_report"].args


def test_same_title_same_second_never_shares_a_file(snapshot, tmp_path, monkeypatch):
    from datetime import datetime, timezone

    class Frozen(datetime):  # both builds land in the very same second
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 26, 5, 9, 41, tzinfo=timezone.utc)

    monkeypatch.setattr(reports, "datetime", Frozen)
    a = reports.build_pdf(snapshot, "Karachi Storm Watch", "victim text", out_dir=tmp_path, owner="victim")
    b = reports.build_pdf(snapshot, "Karachi Storm Watch", "attacker text", out_dir=tmp_path, owner="attacker")
    assert a != b and a.exists() and b.exists()
    assert [e["file"] for e in reports.visible_index("victim", out_dir=tmp_path)] == [a.name]
    assert [e["file"] for e in reports.visible_index("attacker", out_dir=tmp_path)] == [b.name]


@pytest.mark.parametrize("placeholder", sorted(access.PLACEHOLDER_PASSWORDS))
def test_example_passwords_never_unlock(monkeypatch, placeholder):
    monkeypatch.setenv("ADMIN_PASSWORD", placeholder)
    ok, reason = access.owner_mode_status()
    assert not ok and "example value" in reason
    ss: dict = {}
    assert access.try_unlock(placeholder, ss)[0] is False and not ss.get("is_owner")


def test_agent_tool_errors_hide_raw_details_from_visitors(monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("chroma internal: /mount/data/chroma sqlite locked")

    monkeypatch.setattr(vector_store, "search", broken)
    public = {t.name: t for t in tools.all_tools(owner="v1")}["search_past_analyses"].invoke({"query": "x"})
    owner = {t.name: t for t in tools.all_tools(owner="v1", see_all=True)}["search_past_analyses"].invoke({"query": "x"})
    assert "chroma internal" not in public and "unavailable" in public
    assert "chroma internal" in owner


def test_failed_answer_details_are_owner_only(monkeypatch):
    from weather_agent.ui import state
    from weather_agent.ui.views import analyst

    exc = RuntimeError("503 UNAVAILABLE {'error': {'code': 503, 'message': 'internal quota detail'}}")
    monkeypatch.setattr(state, "is_owner", lambda: False)
    assert "internal quota detail" not in analyst._friendly_error(exc, ["m1"])
    monkeypatch.setattr(state, "is_owner", lambda: True)
    assert "internal quota detail" in analyst._friendly_error(exc, ["m1"])
