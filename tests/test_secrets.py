import pytest
from desktop_pet.secrets import put_secret, get_secret
from desktop_pet.ai import Companion, validate_endpoint
from desktop_pet.storage import Settings


def test_plaintext_keyring_backends_are_never_used(monkeypatch):
    import keyring

    class Backend:
        pass

    Backend.__module__ = "keyrings.alt.file"
    monkeypatch.setattr(keyring, "get_keyring", lambda: Backend())
    calls = []
    monkeypatch.setattr(keyring, "set_password", lambda *args: calls.append(args))
    with pytest.raises(RuntimeError, match="file-based"):
        put_secret("test", "not-a-real-key")
    with pytest.raises(RuntimeError):
        get_secret("test")
    assert calls == []


def test_failed_key_removal_is_reported_instead_of_claimed_success(
    app, tmp_path, monkeypatch
):
    import keyring

    companion = Companion(Settings(tmp_path))
    companion.key = "session"
    companion.remember_key = True
    monkeypatch.setattr(
        keyring,
        "delete_password",
        lambda *args: (_ for _ in ()).throw(RuntimeError("Backend unavailable")),
    )
    with pytest.raises(RuntimeError, match="could not be removed"):
        companion.save_key("", False)
    assert companion.remember_key is True
    companion.shutdown()


def test_invalid_url_port_error_never_echoes_the_entered_secret():
    with pytest.raises(ValueError) as error:
        validate_endpoint("https://example.test:private-token")
    assert "private-token" not in str(error.value)
