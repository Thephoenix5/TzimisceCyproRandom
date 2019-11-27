"""Database handler for rolls stored rolls."""

import os
import re
import psycopg2


class RollDB:
    """Handles stored rolls, including creation, deletion, listing, and modification."""

    def __init__(self):
        self.conn = psycopg2.connect(os.environ["DATABASE_URL"], sslmode="require")
        self.cursor = self.conn.cursor()

        # The main table for storing rolls.
        self.cursor.execute(
            """CREATE TABLE IF NOT EXISTS SavedRolls
                              (ID     bigint NOT NULL,
                               Name   Text   NOT NULL,
                               Syntax Text   NOT NULL,
                               Guild  bigint NOT NULL);"""
        )

        # This table is just used for statistics purposes.
        self.cursor.execute(
            """CREATE TABLE IF NOT EXISTS Guilds
                              (ID    bigint PRIMARY KEY,
                               NAME  Text   NOT NULL,
                               Rolls int    NOT NULL DEFAULT 0);"""
        )

        self.conn.commit()

    def query_saved_rolls(self, guild, userid, message):
        """Parses the message to see what kind of query is needed, then performs it."""

        # Store a new roll or change an old one.
        pattern = re.compile(
            r"^[/!]mw?\s+(?P<name>\w+)\s*=\s*(?P<syn>\d+\s*(?:\d+)?\s*[\w\s]*|\d+(d\d+)?(\+(\d+|\d+d\d+))*)$"
        )
        match = pattern.match(message)
        if match:
            name = match.group("name")
            syntax = match.group("syn")
            return self.store_roll(guild, userid, name, syntax)

        # Use a stored roll.
        pattern = re.compile(
            r"^[/!]m(?P<will>w)?\s+(?P<name>\w+)\s*(?:#\s*(?P<comment>.*))?$"
        )
        match = pattern.match(message)
        if match:
            name = match.group("name")
            will = match.group("will")
            syntax = self.retrieve_stored_roll(guild, userid, name)

            if not syntax:
                return "Roll doesn't exist!"

            comment = match.group("comment")

            roll = "!m " if not will else "!mw "
            roll += syntax

            if comment:
                roll += " # " + comment
            else:
                roll += " # " + name  # Provide a default comment

            return roll

        # Delete a stored roll.
        pattern = re.compile(r"^[/!]mw?\s+(?P<name>\w+)\s*=\s*$")
        match = pattern.match(message)
        if match:
            name = match.group("name")
            return self.delete_stored_roll(guild, userid, name)

        # We have no idea what the user wanted to do.
        return "Come again?"

    def store_roll(self, guild, userid, name, syntax):
        """Store a new roll, or update an old one."""
        if not self.__is_roll_stored(guild, userid, name):
            # Create the roll
            query = "INSERT INTO SavedRolls VALUES (%s, %s, %s, %s);"
            self.cursor.execute(query, (userid, name, syntax, guild,))
            self.conn.commit()

            return "New roll saved!"

        # Update an old roll
        query = "UPDATE SavedRolls SET Syntax=%s WHERE ID=%s AND Name=%s;"
        self.cursor.execute(query, (syntax, userid, name,))
        self.conn.commit()

        return "Roll updated!"

    def retrieve_stored_roll(self, guild, userid, name):
        """Returns the Syntax for a stored roll."""
        query = "SELECT Syntax FROM SavedRolls WHERE Guild=%s AND ID=%s AND Name=%s;"
        self.cursor.execute(query, (guild, userid, name,))
        result = self.cursor.fetchone()

        if not result:
            return None

        return result[0]

    def delete_stored_roll(self, guild, userid, name):
        """Delete a stored roll."""
        if not self.__is_roll_stored(guild, userid, name):
            return "Can't delete. Roll not found!"

        query = "DELETE FROM SavedRolls WHERE Guild=%s AND ID=%s AND Name=%s;"
        self.cursor.execute(query, (guild, userid, name,))
        self.conn.commit()

        return "Roll deleted!"

    def stored_rolls(self, guild, userid):
        """Returns an list of all the stored rolls."""
        query = "SELECT Name, Syntax FROM SavedRolls WHERE Guild=%s AND ID=%s ORDER BY Name;"
        self.cursor.execute(query, (guild, userid,))
        results = self.cursor.fetchall()

        fields = []
        for row in results:
            fields.append((row[0], row[1]))

        return fields

    def __is_roll_stored(self, guild, userid, name):
        """Returns true if a roll by the given name has been stored."""
        return self.retrieve_stored_roll(guild, userid, name) is not None

    def add_guild(self, guildid, name):
        """Adds a guild to the Guilds table."""
        query = "INSERT INTO Guilds VALUES (%s, %s);"

        self.cursor.execute(query, (guildid, name,))
        self.conn.commit()

    def remove_guild(self, guildid):
        """Removes a guild from the Guilds table."""
        query = "DELETE FROM Guilds WHERE ID=%s;"

        self.cursor.execute(query, (guildid,))
        self.conn.commit()

    def rename_guild(self, guildid, name):
        """Updates the name of a guild in the Guilds table."""
        query = "UPDATE Guilds SET Name=%s WHERE ID=%s;"

        self.cursor.execute(query, (name, guildid,))
        self.conn.commit()

    def increment_rolls(self, guildid):
        """Keep track of the number of rolls performed on each server."""
        query = "UPDATE Guilds SET Rolls = Rolls + 1 WHERE ID=%s;"

        self.cursor.execute(query, (guildid,))
        self.conn.commit()
