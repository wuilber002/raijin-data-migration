#!/usr/bin/env python3

import csv
import json
import re
import urllib.request
from decimal import Decimal
from pathlib import Path


REGIONS = ["sa-east-1", "us-east-1"]

BASE_URL = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws"


def download_json(service: str, region: str, cache_dir: Path) -> dict:
    cache_dir.mkdir(parents=True, exist_ok=True)
    file_path = cache_dir / f"{service}-{region}.json"

    url = f"{BASE_URL}/{service}/current/{region}/index.json"

    if file_path.exists():
        print(f"Usando cache: {file_path}")
        return json.loads(file_path.read_text(encoding="utf-8"))

    print(f"Baixando: {url}")
    with urllib.request.urlopen(url) as response:
        data = response.read().decode("utf-8")

    file_path.write_text(data, encoding="utf-8")
    return json.loads(data)


def iter_price_dimensions(price_list: dict):
    products = price_list["products"]
    terms = price_list["terms"]["OnDemand"]

    for sku, product in products.items():
        attrs = product.get("attributes", {})

        sku_terms = terms.get(sku, {})
        for term_code, term in sku_terms.items():
            price_dimensions = term.get("priceDimensions", {})
            for dimension_code, dimension in price_dimensions.items():
                price_usd = dimension["pricePerUnit"].get("USD")

                if price_usd is None:
                    continue

                yield {
                    "sku": sku,
                    "product_family": product.get("productFamily", ""),
                    "location": attrs.get("location", ""),
                    "region_code": attrs.get("regionCode", ""),
                    "storage_class": attrs.get("storageClass", ""),
                    "volume_type": attrs.get("volumeType", ""),
                    "usagetype": attrs.get("usagetype", ""),
                    "operation": attrs.get("operation", ""),
                    "group": attrs.get("group", ""),
                    "group_description": attrs.get("groupDescription", ""),
                    "from_location": attrs.get("fromLocation", ""),
                    "from_location_type": attrs.get("fromLocationType", ""),
                    "to_location": attrs.get("toLocation", ""),
                    "to_location_type": attrs.get("toLocationType", ""),
                    "transfer_type": attrs.get("transferType", ""),
                    "description": dimension.get("description", ""),
                    "unit": dimension.get("unit", ""),
                    "begin_range": dimension.get("beginRange", ""),
                    "end_range": dimension.get("endRange", ""),
                    "price_per_unit_usd": Decimal(price_usd),
                }


def text_blob(row: dict) -> str:
    fields = [
        "product_family",
        "location",
        "region_code",
        "storage_class",
        "volume_type",
        "usagetype",
        "operation",
        "group",
        "group_description",
        "from_location",
        "from_location_type",
        "to_location",
        "to_location_type",
        "transfer_type",
        "description",
        "unit",
    ]
    return " | ".join(str(row.get(f, "")) for f in fields).lower()


def match_all(row: dict, patterns: list[str]) -> bool:
    blob = text_blob(row)
    return all(re.search(pattern.lower(), blob) for pattern in patterns)


def match_any(row: dict, patterns: list[str]) -> bool:
    blob = text_blob(row)
    return any(re.search(pattern.lower(), blob) for pattern in patterns)


def find_candidates(rows: list[dict], must: list[str], any_of: list[str] | None = None):
    result = []

    for row in rows:
        if not match_all(row, must):
            continue

        if any_of and not match_any(row, any_of):
            continue

        result.append(row)

    return result


def first_tier_only(rows: list[dict]):
    result = []
    for row in rows:
        begin = str(row.get("begin_range", ""))
        if begin in ("", "0", "0.0", "0.0000000000"):
            result.append(row)
    return result


def normalize_per_1000(row: dict) -> Decimal:
    """
    AWS Price List pode publicar requests como:
    - unit = Requests
    - preço por 1.000 requests embutido na descrição
    - ou preço por unidade lógica da price dimension

    Para S3 requests, normalmente o valor retornado já representa US$/1.000 requests
    quando a descrição diz "... per 1,000 requests".
    Este script não converte automaticamente quando a descrição é ambígua.
    """
    return row["price_per_unit_usd"]


def print_best(label: str, candidates: list[dict], expected_unit: str | None = None):
    print("\n" + "=" * 100)
    print(label)
    print("=" * 100)

    if not candidates:
        print("Nenhum candidato encontrado.")
        return

    for i, row in enumerate(candidates[:10], start=1):
        print(f"\n[{i}]")
        print(f"SKU:          {row['sku']}")
        print(f"Preço USD:    {row['price_per_unit_usd']}")
        print(f"Unidade:      {row['unit']}")
        print(f"Begin/End:    {row['begin_range']} - {row['end_range']}")
        print(f"StorageClass: {row['storage_class']}")
        print(f"UsageType:    {row['usagetype']}")
        print(f"Operation:    {row['operation']}")
        print(f"Group:        {row['group']}")
        print(f"Group Desc:   {row['group_description']}")
        print(f"Descrição:    {row['description']}")

    if len(candidates) > 10:
        print(f"\n... {len(candidates) - 10} candidatos adicionais omitidos no terminal.")


def audit_region(region: str, cache_dir: Path) -> dict:
    s3 = download_json("AmazonS3", region, cache_dir)
    dt = download_json("AWSDataTransfer", region, cache_dir)

    s3_rows = list(iter_price_dimensions(s3))
    dt_rows = list(iter_price_dimensions(dt))

    results = {}

    # 1. S3 Standard Storage - first tier
    candidates = find_candidates(
        s3_rows,
        must=[
            r"standard",
            r"timedstorage|storage",
            r"byte|gb|gbyte|month",
        ],
        any_of=[
            r"first 50 tb",
            r"first 50 tb / month",
            r"storage used",
            r"standard storage",
        ],
    )
    candidates = first_tier_only(candidates)
    results["S3 Standard storage - first tier US$/GB-month"] = candidates

    # 2. S3 PUT/COPY/POST/LIST
    candidates = find_candidates(
        s3_rows,
        must=[
            r"put|copy|post|list|requests-tier1|tier1",
        ],
        any_of=[
            r"put",
            r"copy",
            r"post",
            r"list",
            r"requests-tier1",
        ],
    )
    results["S3 Standard PUT/COPY/POST/LIST requests US$/1,000"] = candidates

    # 3. S3 GET/SELECT and other
    candidates = find_candidates(
        s3_rows,
        must=[
            r"get|select|requests-tier2|tier2|all other",
        ],
        any_of=[
            r"get",
            r"select",
            r"all other",
            r"requests-tier2",
        ],
    )
    results["S3 Standard GET/SELECT and other requests US$/1,000"] = candidates

    # 4. Deep Archive Bulk data retrieval US$/GB
    candidates = find_candidates(
        s3_rows,
        must=[
            r"deep archive",
            r"bulk",
            r"retrieval",
        ],
        any_of=[
            r"gb",
            r"gbyte",
            r"data retrieval",
            r"bulk retrieval",
        ],
    )
    results["S3 Glacier Deep Archive Bulk data retrieval US$/GB"] = candidates

    # 5. Deep Archive Standard data retrieval US$/GB
    candidates = find_candidates(
        s3_rows,
        must=[
            r"deep archive",
            r"standard",
            r"retrieval",
        ],
        any_of=[
            r"gb",
            r"gbyte",
            r"data retrieval",
            r"standard retrieval",
        ],
    )
    results["S3 Glacier Deep Archive Standard data retrieval US$/GB"] = candidates

    # 6. Deep Archive Bulk restore requests US$/1,000
    candidates = find_candidates(
        s3_rows,
        must=[
            r"deep archive",
            r"bulk",
            r"restore|request",
        ],
        any_of=[
            r"restore",
            r"requests",
            r"bulk",
        ],
    )
    results["S3 Glacier Deep Archive Bulk restore requests US$/1,000"] = candidates

    # 7. Deep Archive Standard restore requests US$/1,000
    candidates = find_candidates(
        s3_rows,
        must=[
            r"deep archive",
            r"standard",
            r"restore|request",
        ],
        any_of=[
            r"restore",
            r"requests",
            r"standard",
        ],
    )
    results["S3 Glacier Deep Archive Standard restore requests US$/1,000"] = candidates

    # 8. Data Transfer OUT to Internet - first tier
    candidates = find_candidates(
        dt_rows,
        must=[
            r"data transfer|datatransfer|out",
            r"internet|external",
        ],
        any_of=[
            r"outbound",
            r"data transfer out",
            r"internet",
            r"external",
        ],
    )
    candidates = first_tier_only(candidates)
    results["Data Transfer OUT to Internet - first tier US$/GB"] = candidates

    return results


def export_audit_csv(all_results: dict, output_file: Path):
    fieldnames = [
        "region",
        "column",
        "candidate_rank",
        "price_per_unit_usd",
        "unit",
        "begin_range",
        "end_range",
        "sku",
        "location",
        "region_code",
        "storage_class",
        "volume_type",
        "usagetype",
        "operation",
        "group",
        "group_description",
        "from_location",
        "from_location_type",
        "to_location",
        "to_location_type",
        "transfer_type",
        "description",
    ]

    with output_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for region, region_results in all_results.items():
            for column, candidates in region_results.items():
                for rank, row in enumerate(candidates, start=1):
                    writer.writerow({
                        "region": region,
                        "column": column,
                        "candidate_rank": rank,
                        "price_per_unit_usd": str(row["price_per_unit_usd"]),
                        "unit": row["unit"],
                        "begin_range": row["begin_range"],
                        "end_range": row["end_range"],
                        "sku": row["sku"],
                        "location": row["location"],
                        "region_code": row["region_code"],
                        "storage_class": row["storage_class"],
                        "volume_type": row["volume_type"],
                        "usagetype": row["usagetype"],
                        "operation": row["operation"],
                        "group": row["group"],
                        "group_description": row["group_description"],
                        "from_location": row["from_location"],
                        "from_location_type": row["from_location_type"],
                        "to_location": row["to_location"],
                        "to_location_type": row["to_location_type"],
                        "transfer_type": row["transfer_type"],
                        "description": row["description"],
                    })


def main():
    cache_dir = Path("aws-price-cache")
    output_file = Path("aws_s3_price_audit.csv")

    all_results = {}

    for region in REGIONS:
        print("\n" + "#" * 100)
        print(f"REGIÃO: {region}")
        print("#" * 100)

        results = audit_region(region, cache_dir)
        all_results[region] = results

        for label, candidates in results.items():
            print_best(f"{region} | {label}", candidates)

    export_audit_csv(all_results, output_file)

    print("\n" + "#" * 100)
    print(f"CSV de auditoria gerado: {output_file.resolve()}")
    print("#" * 100)

    print(
        """
IMPORTANTE:
- Valide manualmente o candidato correto no CSV.
- Data Transfer OUT é por faixa; não use apenas a primeira faixa para 1.500 TB.
- S3 Batch Operations job charge e object charge podem não aparecer de forma regional no JSON.
  A página pública da AWS S3 Pricing documenta:
    - US$ 0.25 por job
    - US$ 1.00 por milhão de objetos processados
  Portanto:
    - object charge = 1 / 1_000_000 = US$ 0.000001 por objeto
"""
    )


if __name__ == "__main__":
    main()
