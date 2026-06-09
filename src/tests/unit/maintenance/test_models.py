import pytest
from maintenance.models import ServiceRequest, ServiceRequestPhoto

from core.constants import ServiceRequestPriority, ServiceRequestStatus
from tests.factories import ServiceRequestFactory, ServiceRequestPhotoFactory


@pytest.mark.django_db
class TestServiceRequestModel:
    def test_create_service_request(self):
        req = ServiceRequestFactory()
        assert req.status == ServiceRequestStatus.OPEN
        assert req.priority == ServiceRequestPriority.MEDIUM
        assert req.assigned_to is None
        assert req.cost is None
        assert req.resolution_notes is None
        assert str(req).startswith("Request #")
        assert req.property is not None
        assert req.tenant is not None

    def test_service_request_soft_delete(self):
        req = ServiceRequestFactory()
        req_id = req.id
        req.delete()
        assert req.deleted_at is not None
        assert not ServiceRequest.objects.filter(id=req_id).exists()
        assert ServiceRequest.deleted_objects.filter(id=req_id).exists()

    def test_assign_request(self):
        from tests.factories import UserFactory

        req = ServiceRequestFactory(status=ServiceRequestStatus.OPEN)
        staff = UserFactory()
        req.assigned_to = staff
        req.status = ServiceRequestStatus.IN_PROGRESS
        req.save()
        req.refresh_from_db()
        assert req.assigned_to == staff
        assert req.status == ServiceRequestStatus.IN_PROGRESS

    def test_resolve_request(self):
        from decimal import Decimal

        req = ServiceRequestFactory(status=ServiceRequestStatus.IN_PROGRESS)
        req.status = ServiceRequestStatus.RESOLVED
        req.cost = Decimal("150.00")
        req.resolution_notes = "Fixed the pipe"
        req.save()
        req.refresh_from_db()
        assert req.status == ServiceRequestStatus.RESOLVED
        assert req.cost == Decimal("150.00")
        assert req.resolution_notes == "Fixed the pipe"

    def test_default_priority_is_medium(self):
        req = ServiceRequestFactory(priority=ServiceRequestPriority.MEDIUM)
        assert req.priority == ServiceRequestPriority.MEDIUM

    def test_all_status_choices(self):
        for status in ServiceRequestStatus.values():
            req = ServiceRequestFactory(status=status)
            assert req.status == status

    def test_all_priority_choices(self):
        for priority in ServiceRequestPriority.values():
            req = ServiceRequestFactory(priority=priority)
            assert req.priority == priority


@pytest.mark.django_db
class TestServiceRequestPhotoModel:
    def test_create_photo(self):
        photo = ServiceRequestPhotoFactory()
        assert photo.service_request is not None
        assert photo.image is not None
        assert str(photo).startswith("Photo #")

    def test_photo_soft_delete(self):
        photo = ServiceRequestPhotoFactory()
        photo_id = photo.id
        photo.delete()
        assert photo.deleted_at is not None
        assert not ServiceRequestPhoto.objects.filter(id=photo_id).exists()
