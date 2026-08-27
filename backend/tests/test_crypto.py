from app.utils.crypto import decrypt_token, encrypt_token


def test_encrypt_decrypt_roundtrip():
    plain = "ghu_dummyTokenValueForTesting1234567890"
    encrypted = encrypt_token(plain)
    assert encrypted != plain
    assert decrypt_token(encrypted) == plain
