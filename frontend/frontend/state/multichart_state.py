"""State for /tools/multichart: how many chart cards the page shows. It starts with one empty card and the full-width
"Add more chart" button adds another (up to MAX_CARDS). The cards themselves are still empty (a + in each)."""

import reflex as rx

MAX_CARDS = 12


class MultichartState(rx.State):
    cards: list[int] = [1]  # one entry per card (its number)

    @rx.var
    def can_add(self) -> bool:
        return len(self.cards) < MAX_CARDS

    @rx.event
    def reset_cards(self):
        """A fresh visit starts with a single card."""
        self.cards = [1]

    @rx.event
    def add_card(self):
        if len(self.cards) < MAX_CARDS:
            self.cards = [*self.cards, len(self.cards) + 1]
