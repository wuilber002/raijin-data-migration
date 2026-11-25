from types import SimpleNamespace

from app import oci_runtime


def test_explicit_namespace_wins_without_calling_oci():
    namespace, source = oci_runtime.resolve_object_storage_namespace(
        object(), {"object_storage_namespace": "configured-namespace"}
    )

    assert namespace == "configured-namespace"
    assert source == "CONFIGURED"


def test_namespace_is_discovered_and_cached_when_not_configured():
    oci_runtime.clear_namespace_cache()
    calls = []

    class FakeClient:
        def get_namespace(self):
            calls.append("get_namespace")
            return SimpleNamespace(data="tenancy-namespace")

    client = FakeClient()
    runtime = {"object_storage_endpoint_url": "https://objectstorage.example"}
    first = oci_runtime.resolve_object_storage_namespace(object(), runtime, client=client)
    second = oci_runtime.resolve_object_storage_namespace(object(), runtime, client=client)

    assert first == ("tenancy-namespace", "AUTO_DISCOVERED")
    assert second == ("tenancy-namespace", "AUTO_DISCOVERED")
    assert calls == ["get_namespace"]
