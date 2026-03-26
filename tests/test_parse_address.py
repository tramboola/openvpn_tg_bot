from ovpn_bot.docker_logic import parse_address


def test_parse_address_valid_cases() -> None:
    assert parse_address("udp://192.168.0.1:8080") == ("udp", "192.168.0.1", "8080")
    assert parse_address("tcp://rwlist.io:443") == ("tcp", "rwlist.io", "443")


def test_parse_address_invalid_case() -> None:
    assert parse_address("invalid-address") is None

