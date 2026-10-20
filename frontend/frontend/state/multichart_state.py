"""State for /tools/multichart: which chart cards the page shows. It starts with one empty card; the full-width
"Add more chart" button adds another (up to MAX_CARDS) and, once there is more than one card, every card has an x at its
top right that removes it (the last card can't be removed). The cards themselves are still empty (a + in each)."""

import reflex as rx

MAX_CARDS = 12


class MultichartState(rx.State):
    cards: list[int] = [1]  # one id per card, never reused
    next_id: int = 2

    @rx.var
    def can_add(self) -> bool:
        return len(self.cards) < MAX_CARDS

    @rx.var
    def can_remove(self) -> bool:
        return len(self.cards) > 1

    @rx.event
    def reset_cards(self):
        """A fresh visit starts with a single card."""
        self.cards = [1]
        self.next_id = 2

    @rx.event
    def add_card(self):
        if len(self.cards) < MAX_CARDS:
            self.cards = [*self.cards, self.next_id]
            self.next_id += 1

    @rx.event
    def remove_card(self, card_id: int):
        if len(self.cards) > 1:
            self.cards = [c for c in self.cards if c != card_id]
