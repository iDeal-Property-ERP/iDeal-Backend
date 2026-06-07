from core.api.views import GenericController


class HealthAPIView(GenericController):
    auth = ()

    def get(self) -> dict:
        return self.ok({"status": "ok"})


class TestAPIView(GenericController):
    auth = ()

    def get(self) -> dict:
        return self.ok({"message": "This is a test endpoint."})
