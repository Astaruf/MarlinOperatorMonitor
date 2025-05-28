import requests
from tabulate import tabulate
import argparse
import csv
import json
import sys
from io import StringIO
import re

POND_TOKEN_ID = "0x5802add45f8ec0a524470683e7295faacc853f97cf4a8d3ffbaaf25ce0fd87c4"
MPOND_TOKEN_ID = "0x1635815984abab0dbb9afd77984dad69c24bf3d711bc0ddb1e2d53ef2d523e5e"
GRAPH_SUBGRAPH_ID = "GUh83DEwZWMTkKaydusdkb46mLuAC7FTL4km1bcNjugc"

def get_marlin_api_key():
    try:
        resp = requests.get("https://arb1.marlin.org/relay/operator")
        resp.raise_for_status()
        import re
        match = re.search(r'src="/(main\.[a-z0-9]+\.js)"', resp.text)
        if not match:
            return None
        js_url = f"https://arb1.marlin.org/{match.group(1)}"
        js_resp = requests.get(js_url)
        js_resp.raise_for_status()
        match = re.search(r'relay_graphql_service_url:"https://gateway-arbitrum\.network\.thegraph\.com/api/([a-f0-9]{32})/subgraphs/id', js_resp.text)
        if match:
            return match.group(1)
    except:
        return None
    return None

def get_graphql_url():
    key = get_marlin_api_key()
    if not key:
        key = "eecb07a46bba6483dbdbd042493c43dc"  # fallback
    return f"https://gateway-arbitrum.network.thegraph.com/api/{key}/subgraphs/id/{GRAPH_SUBGRAPH_ID}"

def fetch_json(url):
    r = requests.get(url)
    r.raise_for_status()
    return r.json()

def fetch_graphql(query, variables, url):
    r = requests.post(url, json={"query": query, "variables": variables})
    r.raise_for_status()
    return r.json()

def format_stake(value, token):
    try:
        val = float(value)
    except Exception:
        return str(value)
    if token == "POND":
        if val > 1e6:
            return f"{val/1e6:.2f}M POND"
        elif val > 1e3:
            return f"{val/1e3:.2f}k POND"
        else:
            return f"{val:.2f} POND"
    elif token == "MPOND":
        return f"{val:.3e} MPOND"
    else:
        return str(value)

def get_operator_data():
    rewards_url = "https://sk.arb1.marlin.org/getExpectedReward"
    cluster_url = "https://sk.arb1.marlin.org/getClusterInfo"
    operators_url = "https://sk.arb1.marlin.org/getVerifiedOperators"
    graphql_url = get_graphql_url()

    rewards = fetch_json(rewards_url)
    cluster = fetch_json(cluster_url)
    operators = fetch_json(operators_url)

    query = """
    query getCluster($pageSize: Int, $pageNo: Int) {
        clusters(where: {status: \"REGISTERED\"}, first: $pageSize, skip: $pageNo) {
            id
            commission
            totalDelegations {
                token {
                    tokenId
                }
                amount
            }
        }
    }
    """
    variables = {"pageSize": 1000, "pageNo": 0}
    graphql_response = fetch_graphql(query, variables, graphql_url)

    cluster_details = {}
    for c in graphql_response['data']['clusters']:
        cluster_details[c['id']] = c

    rows = []
    for addr, rew in rewards.items():
        info = cluster.get(addr, {})
        operator_name = operators.get(addr, "Unknown")

        commission = "N/A"
        stake_pond_raw = 0.0
        stake_mpond_raw = 0.0
        if addr in cluster_details:
            commission = cluster_details[addr].get("commission", "N/A")
            delegs = cluster_details[addr].get("totalDelegations", [])
            for d in delegs:
                token_id = d["token"]["tokenId"]
                amount = float(d["amount"])
                if token_id == POND_TOKEN_ID:
                    stake_pond_raw = amount / 1e18
                elif token_id == MPOND_TOKEN_ID:
                    stake_mpond_raw = amount / 1e18

        total_pond_raw = stake_pond_raw + (stake_mpond_raw * 1e6)

        row = [
            operator_name,
            info.get("network", "N/A"),
            addr,
            format_stake(total_pond_raw, "POND"),
            format_stake(stake_pond_raw, "POND"),
            format_stake(stake_mpond_raw, "MPOND"),
            info.get("relayers", "N/A"),
            commission,
            info.get("latencyScore", "N/A"),
            info.get("tickets", "N/A"),
            rew.get("MPOND", 0),
            rew.get("POND", 0),
            total_pond_raw
        ]
        rows.append(row)

    return rows

def sort_data(rows, column, descending):
    if column in (3, 4, 5):
        return sorted(rows, key=lambda x: x[12], reverse=descending)
    elif column in (6, 7, 8, 9, 10, 11):
        return sorted(rows, key=lambda x: float(x[column]), reverse=descending)
    else:
        return sorted(rows, key=lambda x: str(x[column]), reverse=descending)

def output_data(rows, headers, output_format):
    trimmed = [r[:-1] for r in rows]
    if output_format == "table":
        print(tabulate(trimmed, headers=headers, tablefmt="grid"))
    elif output_format == "csv":
        writer = csv.writer(sys.stdout)
        writer.writerow(headers)
        writer.writerows(trimmed)
    elif output_format == "tsv":
        writer = csv.writer(sys.stdout, delimiter='\t')
        writer.writerow(headers)
        writer.writerows(trimmed)
    elif output_format == "json":
        json_data = [dict(zip(headers, row)) for row in trimmed]
        print(json.dumps(json_data, indent=2))
    elif output_format == "markdown":
        print(tabulate(trimmed, headers=headers, tablefmt="github"))
    else:
        raise ValueError(f"Formato output non supportato: {output_format}")

def parse_args():
    parser = argparse.ArgumentParser(description="Marlin Operator Monitor")
    parser.add_argument('-f', '--filter', type=int, default=3, help="Column index to sort by (default 3)")
    parser.add_argument('-o', '--order', choices=["asc", "desc"], default="desc")
    parser.add_argument('--format', choices=["table", "csv", "json", "tsv", "markdown"], default="table")
    return parser.parse_args()

def main():
    args = parse_args()
    rows = get_operator_data()
    rows = sort_data(rows, args.filter, args.order == "desc")

    headers = [
        "Operator",
        "Network",
        "Address",
        "Total Staked POND",
        "Staked POND",
        "Staked MPond",
        "Relayers",
        "Fee (%)",
        "Performance",
        "Tickets",
        "APR MPond (%)",
        "APR POND (%)",
    ]

    output_data(rows, headers, args.format)

if __name__ == "__main__":
    main()
