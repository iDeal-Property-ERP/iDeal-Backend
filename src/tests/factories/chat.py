import factory
from chat.models import Conversation, ConversationReport, Message

from core.constants import ChatMessageKind, ChatReportReason, ChatSenderSide

from .account import TenantFactory, UserFactory
from .marketplace import ListingFactory


class ConversationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Conversation

    listing = factory.SubFactory(ListingFactory)
    user = factory.SubFactory(TenantFactory)


class MessageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Message

    conversation = factory.SubFactory(ConversationFactory)
    sender_side = ChatSenderSide.USER

    @factory.lazy_attribute
    def sender(self):
        if self.sender_side == ChatSenderSide.USER:
            return self.conversation.user
        return UserFactory()

    kind = ChatMessageKind.TEXT
    text = factory.Faker("text", max_nb_chars=1024)


class ConversationReportFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ConversationReport

    conversation = factory.SubFactory(ConversationFactory)
    reported_by = factory.SubFactory(TenantFactory)
    reason = ChatReportReason.SPAM
    note = factory.Faker("text", max_nb_chars=500)
