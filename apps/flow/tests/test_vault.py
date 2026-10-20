"""The automations' secrets box (WORKBOOK FLOW-F26; old hub HUB-F99, ``secret_box.rs``): a value is sealed
with Fernet under ``settings.FLOW_SECRETS_KEY`` and only opened to make a call; what a call leaves (its
answer, its error) hides every secret it used."""

import pytest
from cryptography.fernet import Fernet

from apps.flow import vault

KEY = Fernet.generate_key().decode()


@pytest.fixture
def key(settings):
    settings.FLOW_SECRETS_KEY = KEY
    return KEY


def test_a_value_is_sealed_and_opened_with_the_servers_key(key):
    token = vault.seal("sk_live_123")
    assert "sk_live_123" not in token
    assert vault.open_value(token) == "sk_live_123"
    assert vault.seal("sk_live_123") != token  # a fresh token every time


def test_without_a_key_nothing_is_kept(settings):
    settings.FLOW_SECRETS_KEY = ""
    assert vault.available() is False
    with pytest.raises(vault.Unavailable):
        vault.seal("x")
    settings.FLOW_SECRETS_KEY = "not a fernet key"
    assert vault.available() is False


def test_a_token_another_key_sealed_cannot_be_opened(key, settings):
    token = vault.seal("sk_live_123")
    settings.FLOW_SECRETS_KEY = Fernet.generate_key().decode()
    with pytest.raises(vault.Unreadable):
        vault.open_value(token)
    settings.FLOW_SECRETS_KEY = ""
    with pytest.raises(vault.Unavailable):
        vault.open_value(token)


def test_masking_hides_every_secret_in_text_and_in_data():
    assert vault.mask("token sk_1 and sk_12", ["sk_1", "sk_12"]) == f"token {vault.MASK} and {vault.MASK}"
    assert vault.mask("nothing", ["", "x" * 0]) == "nothing"
    data = {"echo": "Bearer sk_12", "list": ["sk_12", 3, None], "sk_12": True}
    assert vault.mask_any(data, ["sk_12"]) == {
        "echo": f"Bearer {vault.MASK}",
        "list": [vault.MASK, 3, None],
        vault.MASK: True,
    }
