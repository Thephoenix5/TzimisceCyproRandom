"""settings.py - Database for managing server settings."""

from collections import defaultdict
from distutils.util import strtobool

from .base import Database

class SettingsDB(Database):
    """Interface for setting and retrieving server parameters."""

    # Non-boolean keys
    DEFAULT_DIFF = "default_diff"
    PREFIX = "prefix"
    XPL_ALWAYS = "xpl_always"
    NEVER_DOUBLE = "never_double"
    NULLIFY_ONES = "nullify_ones"
    NO_BOTCH = "no_botch"
    CHRONICLES = "chronicles"

    __PARAMETERS = {
        PREFIX: "Defines the bot invocation prefix.",
        "use_compact": "Set the server to always use compact rolls.",
        DEFAULT_DIFF: "The default difficulty for a pool-based roll.",
        "xpl_always": "If `true`, tens always explode.",
        XPL_ALWAYS: "If `true`, specialty tens explode.",
        NEVER_DOUBLE: "If `true`, tens will never count as double successes.",
        "always_double": "If `true`, tens will always count as double successes.",
        NULLIFY_ONES: "If `true`, the `z` roll option causes ones to not subtract successes.",
        NO_BOTCH: "Permanently disables botches.",
        "wp_cancelable": "Allows ones to cancel a Willpower success.",
        CHRONICLES: "Enables Chronicles of Darkness-style rolls."
    }

    def __init__(self):
        super().__init__()

        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS GuildSettings(
                ID                bigint  PRIMARY KEY,
                Prefix            Text,
                use_compact       boolean DEFAULT FALSE,
                xpl_spec          boolean DEFAULT FALSE,
                nullify_ones      boolean DEFAULT FALSE,
                xpl_always        boolean DEFAULT FALSE,
                never_double      boolean DEFAULT FALSE,
                always_double     boolean DEFAULT FALSE,
                default_diff      int     DEFAULT 6,
                wp_cancelable     boolean DEFAULT FALSE,
                chronicles        boolean DEFAULT FALSE,
                no_botch          boolean DEFAULT FALSE
            )
            """
        )
        self.__all_settings = self.__fetch_all_settings()


    def __fetch_all_settings(self) -> dict:
        """Fetch settings for each server."""
        query_cols = ", ".join(self.available_parameters)
        query = f"SELECT ID, {query_cols} FROM GuildSettings;"
        self._execute(query)
        results = self.cursor.fetchall()

        default_params = defaultdict(lambda: False)
        default_params[self.DEFAULT_DIFF] = 6
        default_params[self.PREFIX] = None
        settings = defaultdict(lambda: default_params)

        for row in results:
            row = list(row)
            guild = row.pop(0)

            parameters = {}
            for i, param in enumerate(self.available_parameters):
                parameters[param] = row[i]

            settings[guild] = parameters

        return settings


    def settings_for_guild(self, guild) -> dict:
        """Fetch the settings for a specific server."""
        if guild and not isinstance(guild, int):
            guild = guild.id

        return self.__all_settings[guild]


    def get_prefixes(self, guild) -> tuple:
        """Returns the guild's prefix. If the guild is None, returns a default."""
        if guild and not isinstance(guild, int):
            guild = guild.id

        prefix = self.settings_for_guild(guild)[SettingsDB.PREFIX]
        if prefix:
            return (prefix,)
        return ("!m", "/m")


    def update(self, guild, key, value) -> str:
        """Sets a server parameter."""
        value = self.__validated_parameter(key, value) # Raises ValueError if invalid

        # Normally unsafe, but we do input validation before we get here
        query = f"UPDATE GuildSettings SET {key}=%s WHERE ID=%s;"
        self._execute(query, value, guild)
        self.__all_settings[guild][key] = value

        message = f"Setting `{key}` to `{value}`!"
        if key == self.PREFIX:
            if value:
                message = f"Setting the prefix to `{value}`."
                if len(value) > 3:
                    message += " A prefix this long might be annoying to type!"
            else:
                message = "Reset the command prefix to `/m` and `!m`."
        elif key == self.CHRONICLES:
            # Also set default difficulty, always explode, nullify ones, no botching
            self.update(guild, self.DEFAULT_DIFF, 8 if value else 6)
            self.update(guild, self.XPL_ALWAYS, str(value))
            self.update(guild, self.NULLIFY_ONES, str(value))
            self.update(guild, self.NO_BOTCH, str(value))

            message = "Enabling" if value else "Disabling"
            message += " Chronicles of Darkness mode."

        return message


    def value(self, guild, key):
        """Retrieves a value for a specific key for a given guild."""
        if key not in self.available_parameters:
            raise ValueError(f"Unknown setting `{key}`!")

        if key == SettingsDB.PREFIX:
            return ", ".join(self.get_prefixes(guild))

        return self.__all_settings[guild][key]


    def __validated_parameter(self, key, new_value):
        """Returns the proper value type for the parameter, or None."""
        if key not in self.available_parameters:
            raise ValueError(f"Unknown setting `{key}`!")

        if key == self.DEFAULT_DIFF:
            try:
                new_value = int(new_value)
                if not 2 <= new_value <= 10:
                    raise ValueError
                return new_value
            except ValueError:
                raise ValueError(f"Error! `{key}` must be an integer between 2-10.") from None
        if key == self.PREFIX:
            return new_value

        # All other keys are true/false
        try:
            new_value = bool(strtobool(new_value))
            return new_value
        except ValueError:
            raise ValueError(f"Error! `{key}` must be `true` or `false`!") from None


    @property
    def available_parameters(self):
        """Returns a list of available configuration options."""
        return self.__PARAMETERS.keys()


    def parameter_information(self, param) -> str:
        """Returns a description of what a given parameter does."""
        try:
            return self.__PARAMETERS[param]
        except KeyError:
            return f"Unknown parameter `{param}`!"


    # Housekeeping stuff

    def add_guild(self, guildid):
        """Adds a guild to the GuildSettings table."""
        query = "INSERT INTO GuildSettings VALUES (%s);"
        self._execute(query, guildid)

    def remove_guild(self, guildid):
        """Removes a guild from the GuildSettings table."""
        query = "DELETE FROM GuildSettings WHERE ID=%s;"
        self._execute(query, guildid)
