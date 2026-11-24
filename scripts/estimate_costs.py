"""Estimate monthly hosting cost: Lightsail vs. a single EC2 instance.

    python scripts/estimate_costs.py

Prices come from the public AWS Price List bulk files (no AWS login needed),
region us-east-1, on-demand, Linux. Writes reports/cost_estimate.json.

Not included (small or zero at portfolio traffic, or depends on choices):
data transfer beyond what's bundled, domain registration/DNS, AWS Budgets,
snapshots, taxes, and any free-tier credits.
"""
from __future__ import annotations

import csv
import io
import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

BASE = "https://pricing.us-east-1.amazonaws.com"
REGION = "us-east-1"
HOURS = 744          # 31-day month: the most a month can cost
EBS_GB = 20          # root volume for EC2: OS + Docker images (~1 GB) + data (~0.5 GB) + headroom
OUT = Path("reports/cost_estimate.json")


def offer_url(service: str, fmt: str = "json") -> str:
    with urllib.request.urlopen(f"{BASE}/offers/v1.0/aws/{service}/current/region_index.json") as r:
        url = json.load(r)["regions"][REGION]["currentVersionUrl"]
    return BASE + (url if fmt == "json" else url.replace("index.json", "index.csv"))


def ondemand_prices(offer: dict, match) -> dict[str, float]:
    """usagetype -> USD per unit, for products where match(attributes) is true."""
    out = {}
    for sku, prod in offer["products"].items():
        a = prod.get("attributes", {})
        if not match(a):
            continue
        for term in offer["terms"]["OnDemand"].get(sku, {}).values():
            for dim in term["priceDimensions"].values():
                out[a["usagetype"]] = float(dim["pricePerUnit"]["USD"])
    return out


def lightsail() -> tuple[dict, str]:
    url = offer_url("AmazonLightsail")
    with urllib.request.urlopen(url) as r:
        offer = json.load(r)
    wanted = {"USE1-BundleUsage:1GB": "1 GB RAM, 2 vCPU, 40 GB SSD, 2 TB transfer",
              "USE1-BundleUsage:2GB": "2 GB RAM, 2 vCPU, 60 GB SSD, 3 TB transfer"}
    p = ondemand_prices(offer, lambda a: a.get("usagetype") in wanted)
    return {k: {"spec": wanted[k], "usd_per_hour": p[k], "usd_per_month": round(p[k] * HOURS, 2)}
            for k in wanted}, url


def public_ipv4() -> tuple[float, str]:
    url = offer_url("AmazonVPC")
    with urllib.request.urlopen(url) as r:
        offer = json.load(r)
    p = ondemand_prices(offer, lambda a: a.get("usagetype") == "USE1-PublicIPv4:InUseAddress")
    return p["USE1-PublicIPv4:InUseAddress"], url


def ec2() -> tuple[dict, float, str]:
    """Stream the ~300 MB EC2 CSV; keep only the rows we need."""
    url = offer_url("AmazonEC2", fmt="csv")
    want = {"BoxUsage:t4g.micro", "BoxUsage:t4g.small"}
    inst, gp3 = {}, None
    with urllib.request.urlopen(url) as r:
        text = io.TextIOWrapper(r, encoding="utf-8")
        for _ in range(5):  # metadata lines before the header
            next(text)
        for row in csv.DictReader(text):
            if row["TermType"] != "OnDemand":
                continue
            ut = row["usageType"]
            if (ut in want and row["Operating System"] == "Linux" and row["Tenancy"] == "Shared"
                    and row["CapacityStatus"] == "Used" and row["Pre Installed S/W"] == "NA"):
                inst[row["Instance Type"]] = {"memory": row["Memory"], "vcpu": row["vCPU"],
                                              "usd_per_hour": float(row["PricePerUnit"])}
            elif ut == "EBS:VolumeUsage.gp3":
                gp3 = float(row["PricePerUnit"])
    return inst, gp3, url


def main() -> None:
    ls, ls_url = lightsail()
    ipv4, vpc_url = public_ipv4()
    inst, gp3, ec2_url = ec2()

    ec2_options = {}
    for itype, i in sorted(inst.items()):
        compute = i["usd_per_hour"] * HOURS
        ec2_options[itype] = {
            "spec": f"{i['memory']} RAM, {i['vcpu']} vCPU + {EBS_GB} GB gp3 + public IPv4",
            "compute_usd": round(compute, 2),
            "ebs_usd": round(gp3 * EBS_GB, 2),
            "public_ipv4_usd": round(ipv4 * HOURS, 2),
            "usd_per_month": round(compute + gp3 * EBS_GB + ipv4 * HOURS, 2),
        }

    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "region": REGION,
        "hours_per_month": HOURS,
        "sources": {"lightsail": ls_url, "ec2": ec2_url, "vpc_public_ipv4": vpc_url},
        "unit_prices": {"ebs_gp3_usd_per_gb_month": gp3, "public_ipv4_usd_per_hour": ipv4},
        "lightsail": ls,
        "ec2": ec2_options,
        "excluded": ["data transfer beyond bundle/free allowance", "domain + DNS", "AWS Budgets",
                     "snapshots", "taxes", "free-tier credits"],
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"Monthly estimate ({HOURS} h, {REGION}, on-demand):")
    for k, v in ls.items():
        print(f"  Lightsail {k.split(':')[1]:4} ${v['usd_per_month']:>6.2f}  {v['spec']}")
    for k, v in ec2_options.items():
        print(f"  EC2 {k:10} ${v['usd_per_month']:>6.2f}  {v['spec']}")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
