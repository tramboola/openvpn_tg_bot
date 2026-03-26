from ovpn_bot.docker_logic import (
    adapt_profile_for_protocol,
    build_client_common_name,
    parse_common_name_to_user,
)


def test_adapt_profile_for_udp_replaces_protocol_and_adds_notify() -> None:
    source_profile = "\n".join(
        [
            "client",
            "proto tcp",
            "remote 1.2.3.4 443",
        ]
    )
    adapted_profile = adapt_profile_for_protocol(source_profile, "udp")

    assert "proto udp" in adapted_profile
    assert "proto tcp" not in adapted_profile
    assert "explicit-exit-notify 1" in adapted_profile


def test_adapt_profile_for_tcp_removes_explicit_exit_notify() -> None:
    source_profile = "\n".join(
        [
            "client",
            "proto udp",
            "explicit-exit-notify 1",
            "remote 1.2.3.4 443",
        ]
    )
    adapted_profile = adapt_profile_for_protocol(source_profile, "tcp")

    assert "proto tcp" in adapted_profile
    assert "proto udp" not in adapted_profile
    assert "explicit-exit-notify 1" not in adapted_profile


def test_build_client_common_name_adds_protocol_suffix() -> None:
    assert build_client_common_name("laptop", "tcp") == "laptop_tcp"
    assert build_client_common_name("phone", "udp") == "phone_udp"


def test_build_client_common_name_keeps_existing_suffix() -> None:
    assert build_client_common_name("work_tcp", "tcp") == "work_tcp"
    assert build_client_common_name("work_udp", "udp") == "work_udp"


def test_parse_common_name_to_user_returns_base_name_and_protocol() -> None:
    assert parse_common_name_to_user("laptop_tcp") == ("laptop", "tcp")
    assert parse_common_name_to_user("phone_udp") == ("phone", "udp")
    assert parse_common_name_to_user("legacy") == ("legacy", "unknown")

