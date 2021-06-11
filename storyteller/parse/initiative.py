"""parse/initiative.py - Parses user input when invoking minit."""

import argparse
import io
from typing import Optional
from contextlib import redirect_stderr

import storyteller.engine # pylint: disable=cyclic-import
import storyteller.initiative
from storyteller.initiative import InitiativeManager
from .response import Response


def initiative(ctx, mod: Optional[int], character_name: Optional[str]) -> Response:
    """
    Parse minit input and return appropriate results.
    Args:
        ctx (discord.ext.commands.Context): User message context
        mod (Optional[int]): An initiative modifier
        character_name (Optional[str]): A character to add to initiative
    Returns (Response): The bot's response to the command
    """

    # Craft a usage message
    prefix = storyteller.settings.get_prefixes(ctx.guild)[0]
    usage = "**Initiative Manager Commands**\n"
    usage += f"`{prefix}i` — Show initiative table (if one exists in this channel)\n"
    usage += f"`{prefix}i <mod> <character>` — Roll initiative (character optional)\n"
    usage += f"`{prefix}i dec <action> [-n character] [-c N]` — Declare a character action\n"
    usage += f"`{prefix}i remove [character]` — Remove initiative (character optional)\n"
    usage += f"`{prefix}i reroll` — Reroll all initiatives\n"
    usage += f"`{prefix}i clear` — Clear the table"

    manager = storyteller.initiative.get_table(ctx.channel.id)
    response = Response(Response.INITIATIVE)

    # Not adding a new initiative to the table
    if not mod:
        # If an initiative table exists, display it
        if manager:
            embed = storyteller.engine.build_embed(
                title="Initiative", description=str(manager),
                footer="Commands: remove | clear | reroll | declare",
                fields=[]
            )

            content = None
            if ctx.invoked_with == "reroll":
                content = "Rerolling initiative!"
            response.embed = embed
            response.content = content
            return response

        # With no initiative table, display the help message instead
        response.content = usage
        return response

    # Rolling a new initiative or augmenting an old one
    try:
        if not manager:
            manager = InitiativeManager()

        # If the user supplies a +/- sign on their mod, that means they are augmenting
        # their existing modifier in-place. If they do not supply a sign, they
        # are rolling a new initiative
        is_augmenting = mod[0] == "-" or mod[0] == "+"
        mod = int(mod)

        character_name = character_name or ctx.author.display_name

        init = None
        if not is_augmenting:
            init = manager.add_init(character_name, mod)
            storyteller.initiative.add_table(ctx.channel.id, manager)
        else:
            init = manager.modify_init(character_name, mod)
            if not init:
                response.content = f"{character_name} has no initiative to modify!"
                return response

        # Build the embed
        title = f"{character_name}'s Initiative"

        entry = "entries" if manager.count > 1 else "entry"
        footer = f"{manager.count} {entry} in table. To see initiative: {prefix}i"

        if is_augmenting:
            footer = f"Initiative modified by {mod:+}.\n{footer}"

        embed = storyteller.engine.build_embed(
            title=title, description=str(init), fields=[], footer=footer
        )
        response.embed = embed

        # Track the initiative in the database
        storyteller.initiative.set_initiative(
            ctx.guild.id, ctx.channel.id, character_name, init.mod, init.die
        )
        storyteller.engine.statistics.increment_initiative_rolls(ctx.guild)

        return response
    except ValueError:
        response.content = usage
        return response


def initiative_removal(ctx, character_name: str) -> Response:
    """
    Remove a character from initiative and returns a status response.
    Args:
        ctx (discord.ext.commands.Context): User message context
        character_name (str): The name of the character to remove
    Returns (Response): A confirmation or error message
    """
    manager = storyteller.initiative.get_table(ctx.channel.id)
    response = Response(Response.INITIATIVE)

    if manager:
        character = character_name or ctx.author.display_name
        removed = manager.remove_init(character)
        if removed:
            storyteller.initiative.remove_initiative(ctx.channel.id, character)
            message = f"Removed {character} from initiative!"

            if manager.count == 0:
                storyteller.initiative.remove_table(ctx.channel.id)
                message += "\nNo characters left in initiative. Clearing table."

            response.content = message
        else:
            response.content = f"Unable to remove {character}; not in initiative!"
    else:
        response.content = "Initiative isn't running in this channel!"

    return response


# Initiative Declarations

# This parser is in module scope so it doesn't have to be recreated every time
# someone rolls initiative
parser = argparse.ArgumentParser(exit_on_error=False)
parser.add_argument("action", nargs="*", default=None)
parser.add_argument("-n", "--name", nargs="*", dest="character")
parser.add_argument("-c", "--celerity", nargs="?", type=int, const=1)


def initiative_declare(ctx, args: list):
    """
    Declare an initiative action.
    Args:
        ctx (discord.ext.commands.Context): User message context
        args (list): User-provided arguments
    Raises: AttributeError if there is no initiative set for the channel
            NameError if the given character has no initiative
            SyntaxError if the correct arguments aren't supplied

            For ease of use, these exceptions are mapped to SyntaxError and thrown
    """
    try:
        manager = storyteller.initiative.get_table(ctx.channel.id)

        # argparse can spit out a lot of effor messages to the console, which
        # the user never (and should never) sees. We are going to suppress
        # those messages by writing them to stderr where they belong.
        parsed = None
        stream = io.StringIO()
        with redirect_stderr(stream):
            parsed = parser.parse_args(args)

        # Correctly form a character name, if provided
        character = ctx.author.display_name
        if parsed.character:
            character = " ".join(parsed.character)

        # Assign the declarations

        if not parsed.action and not parsed.celerity:
            raise SyntaxError("You need to supply an action!")

        if parsed.action:
            action = " ".join(parsed.action)
            if not manager.declare_action(character, action):
                raise NameError(character)

            storyteller.initiative.set_initiative_action(
                ctx.channel.id, character, action
            )

        if parsed.celerity:
            if not manager.has_character(character):
                raise NameError(character)

            for _ in range(parsed.celerity):
                manager.add_celerity(character)

    except AttributeError:
        raise SyntaxError("Initiative isn't set in this channel!") from None
    except NameError:
        raise SyntaxError(f"{character} isn't in the initiative table!") from None
    except (SystemExit, argparse.ArgumentError):
        raise SyntaxError("Usage: `/mi dec <action> [-n character] [--celerity N]`") from None
