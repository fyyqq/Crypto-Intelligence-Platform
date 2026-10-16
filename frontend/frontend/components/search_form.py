"""Search bars search on SUBMIT (Enter, a phone keyboard's Go/Search key, or the magnifier icon), never while typing.

A search input is an uncontrolled field inside a form (`name="q"`): typing only changes the field, and the form's submit
hands the text to the state handler. `key` is the committed search text (or a counter the state bumps when it clears the
search), so the field shows the committed text again after a programmatic change such as a clear button.
The form is `display: contents` (styles.css `.search-submit-form`) so it never changes the layout around the field;
assets/instant_ui.js 5 makes the magnifier icon submit the form."""

import reflex as rx


def search_form(*children, on_submit, **props) -> rx.Component:
    """`on_submit` is `lambda form_data: Handler(form_data["q"])` (or a handler taking form_data)."""
    return rx.el.form(*children, on_submit=on_submit, reset_on_submit=False, class_name="search-submit-form", **props)


def q(form_data) -> rx.Var:
    """The submitted search text: `lambda form_data: Handler(q(form_data))`."""
    return form_data.to(dict[str, str])["q"]
