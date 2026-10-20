"""A tiny wrapper around ``st.session_state``.

Keeping every value under one prefix means "start over" is a single loop, and
the page code reads like plain attribute access (``state.target_col``).
"""

from __future__ import annotations

from typing import Iterable

import streamlit as st

__all__ = ["AppState"]

PREFIX = "tf_"


class AppState:
    """Attribute-style access to namespaced session state.

    Missing attributes return ``None`` instead of raising, which keeps the page
    code free of ``if "key" in st.session_state`` noise.  Use :meth:`get` when a
    default other than ``None`` is needed.
    """

    def __init__(self, prefix: str = PREFIX) -> None:
        self.__dict__["_prefix"] = prefix

    # ---------------------------------------------------------------- plumbing
    def _key(self, name: str) -> str:
        return self._prefix + name

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return st.session_state.get(self._key(name))

    def __setattr__(self, name: str, value) -> None:
        if name.startswith("_"):
            self.__dict__[name] = value
            return
        st.session_state[self._key(name)] = value

    def __contains__(self, name: str) -> bool:
        return self._key(name) in st.session_state

    # ------------------------------------------------------------------- API
    def get(self, name: str, default=None):
        value = st.session_state.get(self._key(name))
        return default if value is None else value

    def set_default(self, name: str, default) -> None:
        if self._key(name) not in st.session_state or st.session_state[self._key(name)] is None:
            st.session_state[self._key(name)] = default

    def clear(self, *names: str) -> None:
        """Remove individual values."""
        for name in names:
            st.session_state.pop(self._key(name), None)

    def clear_prefixed(self, extra: Iterable[str] = ()) -> None:
        """Wipe everything this app stored (used by *Start over*)."""
        for key in list(st.session_state.keys()):
            if key.startswith(self._prefix) or key in set(extra):
                del st.session_state[key]

    def snapshot(self) -> dict:
        return {key[len(self._prefix):]: value for key, value in st.session_state.items()
                if key.startswith(self._prefix)}


def widget_keys() -> list:
    """Widget keys this app creates (cleared on *Start over*)."""
    return [
        "upl_data",
        "upl_abbr",
        "data_sheet",
        "data_header",
        "abbr_sheet",
        "abbr_header",
        "abbr_phrase_col",
        "abbr_abbr_col",
        "target_col",
        "step_nav",
        "editor_preview",
        "editor_unknown",
        "editor_mappings",
        "fill_row_ids",
        "fill_row_seq",
    ]
