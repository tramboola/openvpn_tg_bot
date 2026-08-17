from __future__ import annotations

import pytest

from ovpn_bot import docker_logic


def test_profile_filename_suffix_does_not_change_certificate_name() -> None:
    assert docker_logic.build_client_common_name("iphone", "udp") == "iphone_udp"
    assert (
        docker_logic.build_profile_filename("iphone", "prague", "udp")
        == "iphone-prague-udp.ovpn"
    )


def test_protocol_is_always_appended_to_new_certificate_name() -> None:
    assert docker_logic.build_client_common_name("work_udp", "tcp") == "work_udp_tcp"


@pytest.mark.parametrize("profile_name", ["", "a b", "../phone", "телефон", "a" * 33])
def test_profile_name_rejects_non_portable_values(profile_name: str) -> None:
    with pytest.raises(ValueError, match="Profile name"):
        docker_logic.normalize_profile_name(profile_name)


@pytest.mark.parametrize("suffix", ["a b", "../prague", "прага", "a" * 25])
def test_profile_suffix_rejects_non_portable_values(suffix: str) -> None:
    with pytest.raises(ValueError, match="suffix"):
        docker_logic.normalize_profile_suffix(suffix)


def test_empty_suffix_omits_extra_separator() -> None:
    assert docker_logic.build_profile_filename("iphone", "", "tcp") == "iphone-tcp.ovpn"

