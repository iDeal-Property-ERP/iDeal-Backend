from channels.layers import get_channel_layer


def test_chat_channel_layer_socket_timeout_exceeds_redis_poll_interval():
    """Keep Redis idle polls below the socket read timeout."""
    layer = get_channel_layer()
    host = layer.hosts[0]

    assert host["socket_timeout"] > layer.brpop_timeout
