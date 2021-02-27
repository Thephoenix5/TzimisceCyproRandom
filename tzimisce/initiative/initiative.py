"""Manages character initiative."""
from tzimisce import roll

class Initiative:
    """An individual initiative roll."""

    def __init__(self, mod: int, die: int = None, action: str = None):
        self.mod = mod
        self.die = die if die else roll.Traditional.roll(1, 10)[0]
        self.action = action

    def __eq__(self, other):
        return self.init == other.init

    def __lt__(self, other):
        return self.init < other.init

    def __str__(self):
        return f"*{self.die} + {self.mod}:*   **{self.init}**"

    def reroll(self):
        """Reroll initiative."""
        self.die = roll.Traditional.roll(1, 10)[0]
        self.action = None # Reroll means new action

    @property
    def init(self):
        """Returns the initiative score."""
        return self.mod + self.die
