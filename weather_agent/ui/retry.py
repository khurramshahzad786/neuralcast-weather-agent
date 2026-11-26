"""Self-healing error panels: when live data fails to load, keep retrying in the background and
redraw the page as soon as the data source answers again (no click needed)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import streamlit as st

from ..weather_api import WeatherAPIError
from . import components as ui
from . import state

EVERY_S = 20


def failed(key: str, exc: Exception, probe: Callable[[], Any]) -> None:
    """Show the error with a Try again button, and retry ``probe()`` every EVERY_S seconds."""
    st.html(ui.empty(f"⚠ {exc}"))
    st.button("↻ Try again", key=f"retry_{key}", help="Fetch the data again now")  # a click reruns the page
    st.session_state[f"_failed_at_{key}"] = time.monotonic()
    _watch(key, probe)


@st.fragment(run_every=f"{EVERY_S}s")
def _watch(key: str, probe: Callable[[], Any]) -> None:
    # The fragment's first run happens with the failed page itself: only retry on the timed runs.
    if time.monotonic() - st.session_state.get(f"_failed_at_{key}", 0.0) >= EVERY_S - 2:
        try:
            probe()
        except WeatherAPIError:
            pass
        else:
            st.rerun()  # data is back: redraw the whole page
    st.caption(f"↻ Retrying automatically every {EVERY_S} s · last check {state.now_local():%H:%M:%S}")
