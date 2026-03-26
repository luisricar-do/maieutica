from services.ping import ping_response


def test_ping_response_json() -> None:
    assert ping_response() == {"pong": True}
