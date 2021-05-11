"""Database handler for rolls stored rolls."""

import re

import storyteller.parse
from .base import Database


class RollDB(Database):
    """Handles stored rolls, including creation, deletion, listing, and modification."""

    def __init__(self):
        super().__init__()

        # Create the SavedRolls table
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS SavedRolls(
                ID       bigint NOT NULL,
                Name     Text   NOT NULL,
                Syntax   Text   NOT NULL,
                Guild    bigint NOT NULL,
                Comment  Text   NULL,
                macro_id int GENERATED ALWAYS AS IDENTITY,
                PRIMARY KEY(macro_id),
                CONSTRAINT fk_guild
                    FOREIGN KEY (Guild)
                        REFERENCES GuildSettings(ID)
                        ON DELETE CASCADE
            );
            """
        )

        # Install trigrams
        self.cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

        # Macro patterns
        self.storex = re.compile(r"^(?P<name>[\w-]+)\s*=\s*(?P<syntax>.+)$")
        self.commentx = re.compile(r"^(?P<name>[\w-]+)\s+c=(?P<comment>.*)$")
        self.usex = re.compile(r"^(?P<name>[\w-]+)\s*(?P<mods>(?P<sign>[+-])?\d+(?:\s[+-]?\d+)?)?$")
        self.deletex = re.compile(r"^(?P<name>[\w-]+)\s*=$")
        self.multiwordx = re.compile(r"[\w-]+ [\w-]+")


    def query_saved_rolls(self, guild, userid, command):
        """Parses the message to see what kind of query is needed, then performs it."""
        syntax = command["syntax"]
        comment = command["comment"]

        # Store a new roll or change an old one.
        match = self.storex.match(syntax)
        if match:
            syntax = match.group("syntax")
            if storyteller.parse.is_valid_roll(syntax):
                name = match.group("name")
                return self.__store_roll(guild, userid, name, syntax, comment)
            return f"Sorry, `{syntax}` is invalid roll syntax!"

        # Change the comment of a stored roll
        match = self.commentx.match(syntax)
        if match:
            name = match.group("name")
            comment = match.group("comment")
            return self.__update_stored_comment(guild, userid, name, comment)

        # Use a stored roll.
        match = self.usex.match(syntax)
        if match:
            command = self.__match_stored_roll(command, match, guild, userid)
            return command

        # Delete a stored roll.
        match = self.deletex.match(syntax)
        if match:
            name = match.group("name")
            return self.delete_stored_roll(guild, userid, name)

        # See if the user tried to do a multi-word macro
        if self.multiwordx.match(syntax):
            return "Sorry, macro names can't contain spaces!"

        # We have no idea what the user wanted to do.
        return "Come again?"


    def __match_stored_roll(self, command, match, guild, userid):
        """Attempts to pull a roll from the database and modify as needed."""
        name = match.group("name")
        compound = self.retrieve_stored_roll(guild, userid, name)

        if not compound:
            alt = self.__find_similar_macro(guild, userid, name)
            if alt:
                return f"`{name}` not found. Did you mean `{alt}`?"

            return f"Sorry, you have no macro named `{name}`!"

        syntax = compound[0]
        mods = match.group("mods")

        # The user may modify a stored roll by changing the pool, diff, or both
        if mods:
            mods = mods.split()
            pool_mod = int(mods[0])

            if pool_mod != 0 and not match.group("sign"):
                return "Pool modifiers must be zero or have a +/- sign."

            pool_desc = f"Pool {pool_mod:+}. " if pool_mod != 0 else ""

            # Modify the pool first
            syntax = syntax.split()
            if len(syntax) == 1 or not syntax[1][0].isdigit(): # Need a default difficulty
                syntax.insert(1, 6)

            # Set the recalculated pool
            syntax[0] = str(int(syntax[0]) + pool_mod)

            # Modify or replace the difficulty
            diff_desc = ""
            diff_mod = "+0" if len(mods) < 2 else mods[1]

            if diff_mod.isdigit(): # No +/- sign
                syntax[1] = diff_mod
                diff_desc = f"Diff. to {diff_mod}."
            else:
                diff_mod = int(diff_mod)
                current_diff = int(syntax[1])
                syntax[1] = str(current_diff + diff_mod)

                if diff_mod != 0:
                    diff_desc = f"Diff. {diff_mod:+}."

            command["override"] = f"{pool_desc}{diff_desc}" # Notice of override
            syntax = " ".join(syntax)

        # Only use the stored command if a new one isn't given
        command["syntax"] = syntax
        if compound[1] and not command["comment"]:
            command["comment"] = compound[1]

        return command


    def macro_count(self, guildid, userid) -> int:
        """Returns the number of macros associated with the user and guild."""
        # Get the macro count
        query = "SELECT COUNT(*) FROM SavedRolls WHERE Guild=%s AND ID=%s;"
        self._execute(query, guildid, userid)
        macro_count = self.cursor.fetchone()[0]

        return macro_count


    def __store_roll(self, guild, userid, name, syntax, comment):
        """Store a new roll, or update an old one."""
        # pylint: disable=too-many-arguments

        # Inserting a new macro
        if not self.__is_roll_stored(guild, userid, name):
            # Create the roll
            query = "INSERT INTO SavedRolls VALUES (%s, %s, %s, %s, %s);"
            self._execute(query, userid, name, syntax, guild, comment)

            return f"Saved new macro: `{name}`."

        # Updating an old macro

        # Updating both syntax and comment
        if comment:
            query = """
                UPDATE SavedRolls
                SET Syntax=%s, Comment=%s
                WHERE ID=%s AND Guild=%s AND Name ILIKE %s;
            """
            self._execute(query, syntax, comment, userid, guild, name)

            return f"Updated `{name}` syntax and comment."

        # Update only syntax
        query = "UPDATE SavedRolls SET Syntax=%s WHERE ID=%s AND Guild=%s AND Name ILIKE %s;"
        self._execute(query, syntax, userid, guild, name)

        return f"Updated `{name}` syntax."


    def __update_stored_comment(self, guild, userid, name, comment):
        """Set or delete a stored roll's comment"""
        if self.__is_roll_stored(guild, userid, name):
            if len(comment) == 0:
                comment = None

            query = "UPDATE SavedRolls SET Comment=%s WHERE ID=%s AND Guild=%s AND Name ILIKE %s;"
            self._execute(query, comment, userid, guild, name)

            return f"Updated comment for `{name}`."

        return f"Unable to update. You don't have a roll named `{name}`!"


    def retrieve_stored_roll(self, guild, userid, name):
        """Returns the Syntax for a stored roll."""
        query = "SELECT Syntax, Comment FROM SavedRolls WHERE Guild=%s AND ID=%s AND Name ILIKE %s;"
        self._execute(query, guild, userid, name)
        result = self.cursor.fetchone()

        return result


    def __find_similar_macro(self, guild, userid, name):
        query = "SELECT Name FROM SavedRolls WHERE Guild=%s AND ID=%s AND SIMILARITY(Name, %s)>0.2;"
        self._execute(query, guild, userid, name)
        result = self.cursor.fetchone()

        if result:
            return result[0]

        return None


    def delete_stored_roll(self, guild, userid, name):
        """Delete a stored roll."""
        if not self.__is_roll_stored(guild, userid, name):
            return f"Can't delete. `{name}` not found!"

        query = "DELETE FROM SavedRolls WHERE Guild=%s AND ID=%s AND Name ILIKE %s;"
        self._execute(query, guild, userid, name)

        return f"`{name}` deleted! It has also been removed from any meta-macros containing it."


    def delete_user_rolls(self, guild, userid):
        """Deletes all of a user's rolls on a given guild."""
        query = "DELETE FROM SavedRolls WHERE Guild=%s AND ID=%s;"
        self._execute(query, guild, userid)


    def stored_rolls(self, guild, userid):
        """Returns an list of all the stored rolls."""
        query = """SELECT Name, Syntax, Comment FROM SavedRolls WHERE Guild=%s AND ID=%s
                   ORDER BY Name;"""
        self._execute(query, guild, userid)
        results = self.cursor.fetchall()

        fields = []
        for row in results:
            name = row[0]
            syntax = row[1]
            comment = row[2]

            if comment:
                syntax += f" # {comment}"

            fields.append((name, syntax))

        return fields


    def __is_roll_stored(self, guild, userid, name):
        """Returns true if a roll by the given name has been stored."""
        return self.retrieve_stored_roll(guild, userid, name) is not None
