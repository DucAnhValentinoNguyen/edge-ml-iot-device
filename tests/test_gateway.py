import pytest

from gateway import GatewayAdapter, RawTelegram


def telegram(timestamp: float = 1000.0) -> RawTelegram:
    return RawTelegram.from_payload(
        {
            "gateway_id": "gateway-test",
            "source_eurid": "045F694E",
            "rorg": "A5",
            "data_hex": "80B40000",
            "timestamp": timestamp,
        }
    )


def test_unknown_telegram_returns_profile_suggestions() -> None:
    result = GatewayAdapter().ingest(telegram())
    assert result.known_device is False
    assert any(candidate["profile_id"] == "A5-04-03" for candidate in result.candidates)


def test_registered_telegram_is_decoded_and_duplicates_are_removed() -> None:
    adapter = GatewayAdapter()
    adapter.register_device("045F694E", "A5-04-03", "Room sensor", "Room 01")
    first = adapter.ingest(telegram())
    duplicate = adapter.ingest(telegram(1000.05))
    later = adapter.ingest(telegram(1001.0))
    assert first.decoded[0]["key"] == "temperature"
    assert first.known_device is True
    assert duplicate.duplicate is True
    assert later.duplicate is False


def test_invalid_device_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="source_eurid"):
        RawTelegram.from_payload({"gateway_id": "gateway-test", "source_eurid": "not-hex", "rorg": "A5", "data_hex": "80"})
