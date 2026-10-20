"""Operating-system credentials only; never fall back to plaintext token files."""


def _keyring():
    import keyring

    backend = keyring.get_keyring()
    candidates = getattr(backend, "backends", [backend])
    if any(type(item).__module__.startswith("keyrings.alt") for item in candidates):
        raise RuntimeError(
            "A file-based keyring backend is configured. Select an operating-system credential backend."
        )
    return keyring


def get_secret(account):
    return _keyring().get_password("BiscuitCompanion", account)


def put_secret(account, value):
    _keyring().set_password("BiscuitCompanion", account, value)


def delete_secret(account):
    keyring = _keyring()
    try:
        keyring.delete_password("BiscuitCompanion", account)
    except keyring.errors.PasswordDeleteError:
        pass
