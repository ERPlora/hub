"""How the papers of the till name a person who acted: the waiter of a kitchen ticket and the cashier of a receipt.
Kitchen requires Sales, so both read it here."""

from collections.abc import Iterable

from django.contrib.auth import get_user_model


def person_label(who) -> str:
    """A person as a person reads them: their name, else their e-mail; their username (the id of the session) only
    as the last resort; anything else (the platform, an API key) as it is."""
    if who is None:
        return ""
    if hasattr(who, "get_username"):
        return who.get_full_name() or getattr(who, "email", "") or who.get_username()
    return str(who)


def person_names(usernames: Iterable[str]) -> dict[str, str]:
    """The people the apps keep by their username, by the name a person reads. Whoever is not found, or has
    neither a name nor an e-mail, is left out: their username is an internal id, never a name."""
    wanted = {name for name in usernames if name}
    if not wanted:
        return {}
    users = get_user_model()
    found = users.objects.filter(**{f"{users.USERNAME_FIELD}__in": wanted})
    return {user.get_username(): label for user in found if (label := person_label(user)) != user.get_username()}
