"""Creates the AWS side of a Noether deployment with the AWS CLI: one EC2 instance with a fixed address.
Caddy on the instance serves HTTPS under <address>.sslip.io, so no domain has to be bought first.

    python deploy/aws/provision.py --infra    # 1. role, firewall and address
    python deploy/aws/provision.py --env      # 2. store the settings the server needs
    python deploy/aws/provision.py            # 3. start the instance, which builds main
    python deploy/aws/provision.py --update   # later: ship main again

--env reads NEBIUS_API_KEY, NEBIUS_PROJECT_ID and NEBIUS_BASE_URL from .env.local and keeps them in the
SSM parameter /noether/env. Never prints them. Safe to re-run: everything is looked up by name first.
"""
from __future__ import annotations

import json
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REGION = "us-east-1"
NAME = "noether"
PARAM = "/noether/env"
INSTANCE_TYPE = "t3.small"  # the largest cheap type a free-plan account may start; the site is mostly static
WINDOWS_AWS = r"C:\Program Files\Amazon\AWSCLIV2\aws.exe"
AWS = shutil.which("aws") or WINDOWS_AWS
ROOT = Path(__file__).resolve().parents[2]
# The wait lets the fixed address attach first: attaching it drops any download already running.
USER_DATA = """#!/bin/bash
set -eux
sleep 45
dnf install -y git tar xz
git clone --depth 1 https://github.com/omshukla24/Noether.git /opt/noether
bash /opt/noether/deploy/aws/bootstrap.sh
"""


def aws(*args: str, ok_fail: bool = False) -> dict | None:
    done = subprocess.run([AWS, "--region", REGION, "--output", "json", *args], capture_output=True, text=True)
    if done.returncode:
        if ok_fail:
            return None
        sys.exit(f"aws {args[0]} {args[1]} failed: {done.stderr.strip()[:400]}")
    out = done.stdout.strip()
    # A call with nothing to report prints nothing at all.
    return json.loads(out) if out else {}


def as_file(data: dict | list) -> str:
    """Passes JSON by file: quoting it through a Windows command line is not reliable."""
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(data, tmp)
    tmp.close()
    return "file://" + Path(tmp.name).as_posix()


def read_env() -> dict[str, str]:
    pairs = (line.split("=", 1) for line in (ROOT / ".env.local").read_text(encoding="utf-8").splitlines() if "=" in line and not line.startswith("#"))
    return {k.strip(): v.strip() for k, v in pairs}


def ensure_role() -> None:
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"}, "Action": "sts:AssumeRole"}]}
    if not aws("iam", "get-role", "--role-name", NAME, ok_fail=True):
        aws("iam", "create-role", "--role-name", NAME, "--assume-role-policy-document", as_file(trust))
    aws("iam", "attach-role-policy", "--role-name", NAME, "--policy-arn", "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore")
    read_param = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "ssm:GetParameter", "Resource": f"arn:aws:ssm:{REGION}:*:parameter{PARAM}"}]}
    aws("iam", "put-role-policy", "--role-name", NAME, "--policy-name", "read-env", "--policy-document", as_file(read_param))
    if not aws("iam", "get-instance-profile", "--instance-profile-name", NAME, ok_fail=True):
        aws("iam", "create-instance-profile", "--instance-profile-name", NAME)
        aws("iam", "add-role-to-instance-profile", "--instance-profile-name", NAME, "--role-name", NAME)
        time.sleep(15)  # a new instance profile takes a moment to reach EC2


def ensure_security_group() -> str:
    vpc = aws("ec2", "describe-vpcs", "--filters", "Name=isDefault,Values=true")["Vpcs"][0]["VpcId"]
    found = aws("ec2", "describe-security-groups", "--filters", f"Name=group-name,Values={NAME}", f"Name=vpc-id,Values={vpc}")["SecurityGroups"]
    if found:
        return found[0]["GroupId"]
    group = aws("ec2", "create-security-group", "--group-name", NAME, "--description", "Noether site: web traffic only", "--vpc-id", vpc)["GroupId"]
    # UDP 443 is HTTP/3. There is no SSH: the instance is reached through SSM.
    rules = [{"IpProtocol": proto, "FromPort": port, "ToPort": port, "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}
             for proto, port in (("tcp", 80), ("tcp", 443), ("udp", 443))]
    aws("ec2", "authorize-security-group-ingress", "--group-id", group, "--ip-permissions", as_file(rules))
    return group


def ensure_address() -> tuple[str, str]:
    found = aws("ec2", "describe-addresses", "--filters", f"Name=tag:Name,Values={NAME}")["Addresses"]
    if found:
        return found[0]["AllocationId"], found[0]["PublicIp"]
    spec = f"ResourceType=elastic-ip,Tags=[{{Key=Name,Value={NAME}}}]"
    made = aws("ec2", "allocate-address", "--domain", "vpc", "--tag-specifications", spec)
    return made["AllocationId"], made["PublicIp"]


def site_host(ip: str) -> str:
    return f"{NAME}.{ip.replace('.', '-')}.sslip.io"


def put_env(host: str) -> None:
    env = read_env()
    missing = [k for k in ("NEBIUS_API_KEY", "NEBIUS_PROJECT_ID", "NEBIUS_BASE_URL") if not env.get(k)]
    if missing:
        sys.exit(f".env.local has no value for: {', '.join(missing)}")
    current = aws("ssm", "get-parameter", "--name", PARAM, "--with-decryption", ok_fail=True)
    salt = next((l.split("=", 1)[1] for l in current["Parameter"]["Value"].splitlines() if l.startswith("NOETHER_IP_SALT=")), None) if current else None
    keep = {k: env[k] for k in ("NEBIUS_API_KEY", "NEBIUS_PROJECT_ID", "NEBIUS_BASE_URL", "TAVILY_API_KEY", "GITHUB_TOKEN") if env.get(k)}
    keep |= {"NEXT_PUBLIC_SITE_URL": f"https://{host}", "NOETHER_HOST": host, "NOETHER_DATA_DIR": "/var/lib/noether",
             "NOETHER_RUNS_PER_IP_HOUR": "3", "NOETHER_RUNS_PER_DAY": "10", "NOETHER_IP_SALT": salt or secrets.token_hex(16)}
    body = {"Name": PARAM, "Type": "SecureString", "Overwrite": True, "Value": "\n".join(f"{k}={v}" for k, v in keep.items()) + "\n"}
    path = as_file(body)
    try:
        aws("ssm", "put-parameter", "--cli-input-json", path)
    finally:
        Path(path.removeprefix("file://")).unlink(missing_ok=True)


def find_instance() -> dict | None:
    filters = [f"Name=tag:Name,Values={NAME}", "Name=instance-state-name,Values=pending,running,stopped"]
    reservations = aws("ec2", "describe-instances", "--filters", *filters)["Reservations"]
    return reservations[0]["Instances"][0] if reservations else None


def start_instance(group: str, allocation: str) -> str:
    image = aws("ssm", "get-parameter", "--name", "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64")["Parameter"]["Value"]
    script = Path(tempfile.gettempdir()) / "noether-user-data.sh"
    script.write_bytes(USER_DATA.encode())
    made = aws("ec2", "run-instances", "--image-id", image, "--instance-type", INSTANCE_TYPE, "--security-group-ids", group,
               "--iam-instance-profile", f"Name={NAME}", "--user-data", "file://" + script.as_posix(),
               "--metadata-options", "HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=2",
               "--block-device-mappings", "DeviceName=/dev/xvda,Ebs={VolumeSize=30,VolumeType=gp3}",
               "--tag-specifications", f"ResourceType=instance,Tags=[{{Key=Name,Value={NAME}}}]")
    instance = made["Instances"][0]["InstanceId"]
    aws("ec2", "wait", "instance-running", "--instance-ids", instance)
    aws("ec2", "associate-address", "--instance-id", instance, "--allocation-id", allocation)
    return instance


def ship(instance: str) -> None:
    """Runs the bootstrap on the instance through SSM and waits for it."""
    params = as_file({"commands": ["bash /opt/noether/deploy/aws/bootstrap.sh"], "executionTimeout": ["1500"]})
    command = aws("ssm", "send-command", "--instance-ids", instance, "--document-name", "AWS-RunShellScript",
                  "--timeout-seconds", "600", "--parameters", params)["Command"]["CommandId"]
    while True:
        time.sleep(15)
        got = aws("ssm", "get-command-invocation", "--command-id", command, "--instance-id", instance, ok_fail=True)
        if got and got["Status"] not in ("Pending", "InProgress", "Delayed"):
            break
    if got["Status"] != "Success":
        sys.exit(f"bootstrap ended {got['Status']}:\n{got['StandardErrorContent'][-1500:]}")


def main() -> None:
    if "--update" in sys.argv:
        instance = find_instance()
        if not instance:
            sys.exit("nothing deployed yet: run without --update first")
        ship(instance["InstanceId"])
        print("shipped")
        return
    if "--env" in sys.argv:
        put_env(site_host(ensure_address()[1]))
        print("settings saved")
        return
    ensure_role()
    group = ensure_security_group()
    allocation, ip = ensure_address()
    print(f"site https://{site_host(ip)}")
    if "--infra" in sys.argv:
        return
    if not aws("ssm", "get-parameter", "--name", PARAM, ok_fail=True):
        sys.exit("no settings on AWS yet: run with --env first")
    found = find_instance()
    if found:
        ship(found["InstanceId"])
        return
    print(f"instance {start_instance(group, allocation)} is building itself from main (about 6 minutes)")


if __name__ == "__main__":
    main()
