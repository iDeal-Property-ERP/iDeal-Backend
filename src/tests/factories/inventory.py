import factory
from inventory.models import InventoryAct, InventoryActItem, InventoryActPhoto

from core.constants import ConditionRating, InventoryActStatus, InventoryActType

from .account import UserFactory
from .property import PropertyFactory


class InventoryActFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = InventoryAct

    property = factory.SubFactory(PropertyFactory)
    lease = None
    act_type = InventoryActType.GENERAL
    status = InventoryActStatus.FINALIZED
    created_by = factory.SubFactory(UserFactory)
    notes = factory.Faker("text", max_nb_chars=120)


class InventoryActItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = InventoryActItem

    act = factory.SubFactory(InventoryActFactory)
    area = factory.Faker("word")
    condition = ConditionRating.GOOD
    sort_order = 0


class InventoryActPhotoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = InventoryActPhoto

    act = factory.SubFactory(InventoryActFactory)
    image = factory.django.ImageField(color="green")
