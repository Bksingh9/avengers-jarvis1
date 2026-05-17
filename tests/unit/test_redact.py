from avengers.core.redact import contains_pii, redact


def test_email():
    r = redact("ping me at alice@example.com")
    assert "<EMAIL>" in r.text
    assert r.hits == {"EMAIL": 1}


def test_specific_patterns_beat_phone():
    text = "SSN 123-45-6789, card 4111 1111 1111 1111, PAN ABCDE1234F, Aadhaar 1234 5678 9012"
    out = redact(text).text
    assert "<SSN>" in out
    assert "<CARD>" in out
    assert "<PAN>" in out
    assert "<AADHAAR>" in out
    # PHONE label should NOT appear — the specific patterns above ate the digits.
    assert "<PHONE>" not in out


def test_phone_still_catches_normal_numbers():
    r = redact("call +1 555 234 5678")
    assert "<PHONE>" in r.text


def test_contains_pii():
    assert contains_pii("write to me at x@y.com") is True
    assert contains_pii("just some plain text") is False


def test_multi_pass_idempotent():
    once = redact("a@b.com").text
    twice = redact(once).text
    assert once == twice
