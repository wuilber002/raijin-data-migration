#!/usr/bin/env python3

import json
import re
import urllib.request
from pathlib import Path


REGION = "sa-east-1"  # troque para us-east-1 quando quiser gerar a outra linha
BASE_URL = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws"


TARGETS = [
    {
        "column": "Data Transfer OUT para Internet — 1ª faixa US$/GB",
        "service": "AWSDataTransfer",
        "must": ["DataTransfer", "Out", "Internet"],
        "begin_range": "0",
    },
    {
        "column": "S3 Glacier Deep Archive — Bulk data retrieval US$/GB",
        "service": "AmazonS3",
        "must": ["Deep Archive", "Bulk", "Retrieval"],
        "avoid": ["request"],
    },
    {
        "column": "S3 Glacier Deep Archive — Standard data retrieval US$/GB",
        "service": "AmazonS3",
        "must": ["Deep Archive", "Standard", "Retrieval"],
        "avoid": ["request"],
    },
    {
        "column": "S3 Standard storage — 1ª faixa US$/GB-mês",
        "service": "AmazonS3",
        "must": ["TimedStorage", "ByteHrs", "Standard"],
        "begin_range": "0",
    },
    {
        "column": "S3 Standard PUT/COPY/POST/LIST requests US$/1.000",
        "service": "AmazonS3",
        "must": ["Requests-Tier1"],
    },
    {
        "column": "S3 Standard GET/SELECT e outras requests US$/1.000",
        "service": "AmazonS3",
        "must": ["Requests-Tier2"],
    },
    {
        "column": "S3 Batch Operations — job charge US$/job",
        "service": "PUBLIC_S3_PRICING_PAGE",
        "sku_override": "N/A - documented on public S3 Pricing page",
    },
    {
        "column": "S3 Batch Operations — object charge US$/objeto",
        "service": "PUBLIC_S3_PRICING_PAGE",
        "sku_override": "N/A - documented on public S3 Pricing page",
    },
    {
        "column": "S3 Glacier Deep Archive — Bulk restore requests US$/1.000",
        "service": "AmazonS3",
        "must": ["Deep Archive", "Bulk", "Restore", "Request"],
    },
    {
        "column": "S3 Glacier Deep Archive — Standard restore requests US$/1.000",
        "service": "AmazonS3",
        "must": ["Deep Archive", "Standard", "Restore", "Request"],
    },
]


def load_price_list(service: str, region: str) -> dict:
    cache_dir = Path("aws-price-cache")
    cache_dir.mkdir(exist_ok=True)

    path = cache_dir / f"{service}-{region}.json"
    url = f"{BASE_URL}/{service}/current/{region}/index.json"

    if not path.exists():
        print(f"Downloading {url}")
        with urllib.request.urlopen(url) as r:
            path.write_bytes(r.read())

    return json.loads(path.read_text(encoding="utf-8"))


def blob(product: dict, dimension: dict) -> str:
    attrs = product.get("attributes", {})
    parts = [
        product.get("productFamily", ""),
        attrs.get("servicecode", ""),
        attrs.get("location", ""),
        attrs.get("regionCode", ""),
        attrs.get("storageClass", ""),
        attrs.get("volumeType", ""),
        attrs.get("usagetype", ""),
        attrs.get("operation", ""),
        attrs.get("group", ""),
        attrs.get("groupDescription", ""),
        attrs.get("fromLocation", ""),
        attrs.get("toLocation", ""),
        attrs.get("transferType", ""),
        dimension.get("description", ""),
        dimension.get("unit", ""),
        dimension.get("beginRange", ""),
        dimension.get("endRange", ""),
    ]
    return " | ".join(parts)


def iter_dimensions(price_list: dict):
    products = price_list["products"]
    terms = price_list["terms"]["OnDemand"]

    for sku, product in products.items():
        for term in terms.get(sku, {}).values():
            for dim in term.get("priceDimensions", {}).values():
                yield sku, product, dim


def matches(target: dict, product: dict, dimension: dict) -> bool:
    text = blob(product, dimension).lower()

    for term in target.get("must", []):
        if term.lower() not in text:
            return False

    for term in target.get("avoid", []):
        if term.lower() in text:
            return False

    expected_begin = target.get("begin_range")
    if expected_begin is not None:
        begin = str(dimension.get("beginRange", ""))
        if begin not in {expected_begin, "0.0", "0.0000000000"}:
            return False

    return True


def find_sku(target: dict, price_lists: dict) -> str:
    if "sku_override" in target:
        return target["sku_override"]

    service = target["service"]
    price_list = price_lists[service]

    candidates = []

    for sku, product, dimension in iter_dimensions(price_list):
        if matches(target, product, dimension):
            candidates.append((sku, product, dimension))

    if not candidates:
        return "NOT_FOUND"

    if len(candidates) > 1:
        # Mantém o SKU, mas sinaliza que você deve revisar manualmente.
        return f"{candidates[0][0]} | REVIEW_{len(candidates)}_CANDIDATES"

    return candidates[0][0]


def main():
    services = sorted({
        t["service"]
        for t in TARGETS
        if t["service"] not in {"PUBLIC_S3_PRICING_PAGE"}
    })

    price_lists = {
        service: load_price_list(service, REGION)
        for service in services
    }

    product_names_row = [t["column"] for t in TARGETS]
    sku_row = [find_sku(t, price_lists) for t in TARGETS]

    print("\nLinha 1 - nomes dos produtos:")
    print("\t".join(product_names_row))

    print("\nLinha 2 - SKUs:")
    print("\t".join(sku_row))


if __name__ == "__main__":
    main()
