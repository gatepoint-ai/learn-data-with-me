"""Reach the warehouse privately: check where its hostname resolves.

With a private endpoint (Private Service Connect on Google Cloud, PrivateLink
on AWS and Azure) and a private DNS zone, the warehouse hostname resolves to an
internal IP inside your network. Without them, it resolves to a public IP and
the traffic leaves through NAT to the internet.

Run it with no arguments to see made-up lookups from inside and outside the
network. Pass a hostname to check a real one from where you are:

    python private_path_check.py my-instance.example-warehouse.cloud

Python standard library only (ipaddress, socket), no installs.
"""

import ipaddress
import socket
import sys

# Made-up lookups: the same hostname, resolved from two places.
SAMPLE = {
    # 10.0.0.0/8 is private; 203.0.113.0/24 and 198.51.100.0/24 are documentation ranges (RFC 5737)
    "from a pod inside the VPC (private zone in place)": ["10.0.0.2"],
    "from a laptop on the internet": ["203.0.113.19", "198.51.100.88"],
    "from a pod, private zone scoped to the wrong VPC": ["203.0.113.19"],
}


# Internal VPC address space (RFC 1918, plus shared address space used by some clouds).
# ipaddress' is_private is broader: it also counts documentation and reserved ranges.
INTERNAL = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10")]


def internal(ip) -> bool:
    return any(ip in net for net in INTERNAL)


def verdict(addresses: list[str]) -> str:
    ips = [ipaddress.ip_address(a) for a in addresses]
    if all(internal(ip) for ip in ips):
        return "PRIVATE  traffic stays on the internal network"
    if any(internal(ip) for ip in ips):
        return "MIXED    some lookups go public: check the zone and the resolver"
    return "PUBLIC   traffic leaves through NAT to the internet"


def resolve(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    return sorted({i[4][0] for i in infos})


if __name__ == "__main__":
    if len(sys.argv) > 1:
        host = sys.argv[1]
        addrs = resolve(host)
        print(f"{host} -> {', '.join(addrs)}\n   {verdict(addrs)}")
    else:
        host = "abc123.region.p.gcp.example-warehouse.cloud"
        print(f"Where does {host} resolve?\n")
        for where, addrs in SAMPLE.items():
            print(f"   {where}\n      -> {', '.join(addrs):28} {verdict(addrs)}")
        print("\nOnly the first answer is the one you want from your workloads.")
        print("Run the check from where the jobs run, not from your laptop.")
