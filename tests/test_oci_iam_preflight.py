from app.oci_iam_preflight import iam_requirements


def test_iam_requirements_render_least_privilege_statements_by_compartment():
    requirements = iam_requirements({
        "secret_compartment_ocids": ["secret-a"],
        "iam_preflight": {
            "dynamic_group_name": "raijin-vm",
            "policy_compartment_ocid": "policy-root",
            "secret_compartment_ocids": ["secret-b", "secret-a"],
            "destination_buckets": [
                {"compartment_id": "destination-a", "name": "legal"},
                {"compartment_id": "destination-a", "name": "finance"},
                {"compartment_id": "destination-b", "name": "archive"},
            ],
        },
    })

    assert requirements["policy_compartment_ocid"] == "policy-root"
    assert requirements["secret_compartment_ocids"] == ["secret-a", "secret-b"]
    assert requirements["statements"] == [
        "Allow dynamic-group raijin-vm to inspect secret-family in compartment id secret-a",
        "Allow dynamic-group raijin-vm to read secret-bundles in compartment id secret-a",
        "Allow dynamic-group raijin-vm to inspect secret-family in compartment id secret-b",
        "Allow dynamic-group raijin-vm to read secret-bundles in compartment id secret-b",
        "Allow dynamic-group raijin-vm to inspect buckets in compartment id destination-a",
        "Allow dynamic-group raijin-vm to manage objects in compartment id destination-a where any {target.bucket.name='finance', target.bucket.name='legal'}",
        "Allow dynamic-group raijin-vm to inspect buckets in compartment id destination-b",
        "Allow dynamic-group raijin-vm to manage objects in compartment id destination-b where any {target.bucket.name='archive'}",
    ]


def test_iam_requirements_do_not_emit_placeholder_policy_without_group_name():
    requirements = iam_requirements({
        "iam_preflight": {
            "policy_compartment_ocid": "policy-root",
            "destination_buckets": [{"compartment_id": "destination", "name": "target"}],
        },
    })

    assert requirements["statements"] == []
