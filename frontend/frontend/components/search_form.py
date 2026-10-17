"""Search bars search when you STOP TYPING (a short delay after the last key), and at once on Enter, a phone keyboard's
Go/Search key or the magnifier icon.

A search input is an uncontrolled field inside a form (`name="q"`): the browser owns what is typed, so a server reply can
never overwrite or drop characters while you are still typing (the bug of the old always-controlled, debounced inputs),
and the field is never remounted mid-typing. assets/instant_ui.js 5 submits the form ~0.45 s after the last keystroke,
turns the magnifier icon into a submit button, and copies the committed text (the input's `value` attribute, which
`default_value` keeps current) into the field when a clear button or another handler changes it and the field is not
focused. The form is `display: contents` (styles.css `.search-submit-form`) so it never changes the layout around it."""

import reflex as rx


def search_form(*children, on_submit, **props) -> rx.Component:
    """`on_submit` is `lambda form_data: Handler(form_data["q"])` (or a handler taking form_data)."""
    return rx.el.form(*children, on_submit=on_submit, reset_on_submit=False, class_name="search-submit-form", **props)


def q(form_data) -> rx.Var:
    """The submitted search text: `lambda form_data: Handler(q(form_data))`."""
    return form_data.to(dict[str, str])["q"]
