from chat.consumers import ChatConsumer


def test_chat_consumer_preserves_channels_async_consumer_marker():
    """Keep the Channels sync marker separate from the chat sync handler."""
    assert ChatConsumer._sync is False
