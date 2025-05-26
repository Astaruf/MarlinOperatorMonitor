import requests
from tabulate import tabulate
import argparse

POND_TOKEN_ID = "0x5802add45f8ec0a524470683e7295faacc853f97cf4a8d3ffbaaf25ce0fd87c4"
MPOND_TOKEN_ID = "0x1635815984abab0dbb9afd77984dad69c24bf3d711bc0ddb1e2d53ef2d523e5e"

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

def parse_args():
    parser = argparse.ArgumentParser(
        description="MarlinOperatorMonitor - View and sort staking stats from Marlin operators.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Column Index Reference (use with -f / --filter):

  0  - Operator           : Name of the operator node
  1  - Network            : Network connected (mainnet/testnet)
  2  - Address            : Operator address
  3  - Total Staked POND  : Combined stake (POND + MPond)
  4  - Staked POND        : Amount of POND staked
  5  - Staked MPond       : Amount of MPond staked
  6  - Relayers           : Number of active relayers
  7  - Performance        : Node performance score (lower is better)
  8  - Fee (%)            : Commission fee set by operator
  9  - Tickets            : Number of ticket participations
 10  - APR MPond (%)      : Estimated MPond annual reward rate
 11  - APR POND (%)       : Estimated POND annual reward rate
"""
    )

    parser.add_argument(
        '-f', '--filter',
        type=int,
        choices=range(0, 12),
        default=3,
        help="Column index to sort by (see reference below)"
    )
    parser.add_argument(
        '-o', '--order',
        choices=['asc', 'desc'],
        default='desc',
        help="Sort order: 'asc' (ascending) or 'desc' (descending) [default: desc]"
    )
    return parser.parse_args()

def main():
    args = parse_args()

    rewards_url = "https://sk.arb1.marlin.org/getExpectedReward"
    cluster_url = "https://sk.arb1.marlin.org/getClusterInfo"
    operators_url = "https://sk.arb1.marlin.org/getVerifiedOperators"
    graphql_url = "https://gateway-arbitrum.network.thegraph.com/api/eecb07a46bba6483dbdbd042493c43dc/subgraphs/id/GUh83DEwZWMTkKaydusdkb46mLuAC7FTL4km1bcNjugc"

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

    combined = []
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
        stake_pond_readable = format_stake(stake_pond_raw, "POND")
        stake_mpond_readable = format_stake(stake_mpond_raw, "MPOND")

        combined.append([
            operator_name,
            info.get("network", "N/A"),
            addr,
            format_stake(total_pond_raw, "POND"),
            stake_pond_readable,
            stake_mpond_readable,
            info.get("relayers", "N/A"),
            info.get("latencyScore", "N/A"),
            commission,
            info.get("tickets", "N/A"),
            rew.get("MPOND", 0),
            rew.get("POND", 0),
            total_pond_raw
        ])

    reverse = args.order == 'desc'
    if args.filter == 3:
        combined.sort(key=lambda x: x[12], reverse=reverse)
    elif args.filter == 4:
        combined.sort(key=lambda x: x[4], reverse=reverse)
    elif args.filter == 5:
        combined.sort(key=lambda x: x[5], reverse=reverse)
    else:
        combined.sort(key=lambda x: x[args.filter], reverse=reverse)

    headers = [
        "Operator",
        "Network",
        "Address",
        "Total Staked POND",
        "Staked POND",
        "Staked MPond",
        "Relayers",
        "Performance",
        "Fee (%)",
        "Tickets",
        "APR MPond (%)",
        "APR POND (%)",
    ]

    to_print = [row[:-1] for row in combined]
    print(tabulate(to_print, headers=headers, tablefmt="grid"))

if __name__ == "__main__":
    main()
