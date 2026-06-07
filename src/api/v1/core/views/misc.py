from core.api.views import GenericController


class HealthAPIView(GenericController):
    auth = ()

    def get(self) -> dict:
        return {"status": "ok"}


class TestAPIView(GenericController):
    auth = ()

    def get(self) -> dict:
        return {"message": "This is a test endpoint."}
