"""GCP Secret Manager through gcloud, with the value only ever on stdin.

The value never appears in argv (visible to every local process through `ps`),
in the environment, in a log or on stdout. gcloud runs with the account the
caller names, or the one `kit/bundles/gcp/scripts/gcp-account.py` maps to the
project; the active gcloud account is used only when asked for explicitly.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

from . import config

LABELS = "managed-by=bitbucket-access-bootstrap"


class SecretManagerError(RuntimeError):
    pass


def _gcloud_bin() -> str:
    return os.environ.get("BAB_GCLOUD", "gcloud")


def resolve_account(project: str, explicit: str | None, allow_active: bool) -> str | None:
    """The account to pin, or None to let gcloud use its active account."""
    if explicit:
        return explicit
    script = config.GCP_ACCOUNT_SCRIPT
    if script.exists():
        out = subprocess.run(
            [sys.executable, str(script), project], capture_output=True, text=True
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    if allow_active:
        return None
    raise SecretManagerError(
        f"no gcloud account mapped to {project}: pass --account, add the project to "
        "GCP_ACCOUNT_MAP (kit/bundles/gcp/scripts/gcp-account.py), or pass --use-active-account"
    )


def _run(args: list[str], account: str | None, data: bytes | None = None) -> subprocess.CompletedProcess:
    cmd = [_gcloud_bin(), *args, "--quiet"]
    if account:
        cmd.append(f"--account={account}")
    env = dict(os.environ, CLOUDSDK_CORE_DISABLE_PROMPTS="1")
    return subprocess.run(cmd, input=data, capture_output=True, env=env)


def _err(proc: subprocess.CompletedProcess) -> str:
    lines = [l.strip() for l in proc.stderr.decode(errors="replace").splitlines() if l.strip()]
    errors = [l for l in lines if l.startswith("ERROR")]
    return " ".join(errors or lines[-1:]) or f"exit {proc.returncode}"


def secret_exists(project: str, name: str, account: str | None) -> bool:
    proc = _run(["secrets", "describe", name, f"--project={project}", "--format=value(name)"], account)
    if proc.returncode == 0:
        return True
    stderr = proc.stderr.decode(errors="replace")
    if "NOT_FOUND" in stderr or "not found" in stderr.lower():
        return False
    raise SecretManagerError(f"cannot read secret {name} in {project}: {_err(proc)}")


def key_location(kms_key: str) -> str | None:
    match = re.search(r"/locations/([^/]+)/", kms_key or "")
    return match.group(1) if match else None


def resolve_kms_key(project: str, spec: str, locations: str | None, account: str | None) -> str:
    """A full cryptoKeys resource, or `auto:<keyring-glob>/<key>` looked up in the project.

    The lookup lists the key rings of the one location in `locations` and returns
    the first ring matching the glob that holds `<key>`, so one command can target
    projects whose rings carry per-project prefixes.
    """
    if not spec.startswith("auto:"):
        if not re.match(r"^projects/[^/]+/locations/[^/]+/keyRings/[^/]+/cryptoKeys/[^/]+$", spec):
            raise SecretManagerError(f"--kms-key {spec!r} is not a cryptoKeys resource name")
        return spec
    ring_glob, _, key = spec[len("auto:"):].rpartition("/")
    if not ring_glob or not key:
        raise SecretManagerError("--kms-key auto: needs <keyring-glob>/<key>")
    if not locations or "," in locations:
        raise SecretManagerError("--kms-key auto: needs exactly one --secret-locations")
    proc = _run(["kms", "keyrings", "list", f"--location={locations}",
                 f"--project={project}", "--format=value(name)"], account)
    if proc.returncode != 0:
        raise SecretManagerError(f"cannot list key rings in {project}: {_err(proc)}")
    for ring in proc.stdout.decode().split():
        if not fnmatch.fnmatchcase(ring.rsplit("/", 1)[-1], ring_glob):
            continue
        found = _run(["kms", "keys", "describe", key, f"--keyring={ring.rsplit('/', 1)[-1]}",
                      f"--location={locations}", f"--project={project}",
                      "--format=value(name)"], account)
        if found.returncode == 0:
            return f"{ring}/cryptoKeys/{key}"
    raise SecretManagerError(
        f"no key {key!r} in a key ring matching {ring_glob!r} ({project}, {locations}): "
        "apply the project's KMS IaC first"
    )


def create_secret(project: str, name: str, account: str | None,
                  locations: str | None = None, kms_key: str | None = None) -> None:
    """Automatic replication, or user-managed in `locations`, optionally with CMEK.

    Organisations with a gcp.resourceLocations policy (EU only, for example)
    reject automatic replication, which is global. gcloud refuses --kms-key-name
    with user-managed replication, so CMEK goes through a replication policy file
    with customerManagedEncryption on each replica. Created this way, the secret
    matches a Terraform `replication { user_managed { replicas { location,
    customer_managed_encryption } } }` block, which a later import adopts without
    replacing it (replication is ForceNew).
    """
    policy = None
    if kms_key:
        where = locations or key_location(kms_key)
        if not where:
            raise SecretManagerError("CMEK needs --secret-locations")
        replicas = [{"location": loc, "customerManagedEncryption": {"kmsKeyName": kms_key}}
                    for loc in where.split(",")]
        config.ensure_dirs()
        fd, policy = tempfile.mkstemp(prefix="replication-", suffix=".json", dir=config.HOME)
        with os.fdopen(fd, "w") as fh:
            json.dump({"userManaged": {"replicas": replicas}}, fh)
        replication = [f"--replication-policy-file={policy}"]
    elif locations:
        replication = ["--replication-policy=user-managed", f"--locations={locations}"]
    else:
        replication = ["--replication-policy=automatic"]
    try:
        proc = _run(
            ["secrets", "create", name, f"--project={project}", *replication, f"--labels={LABELS}"],
            account,
        )
    finally:
        if policy:
            os.unlink(policy)
    if proc.returncode != 0:
        raise SecretManagerError(f"cannot create secret {name} in {project}: {_err(proc)}")


def add_version(project: str, name: str, value: str, account: str | None) -> str:
    """Add a version from stdin; returns its resource name."""
    proc = _run(
        ["secrets", "versions", "add", name, f"--project={project}",
         "--data-file=-", "--format=value(name)"],
        account,
        data=value.encode(),
    )
    if proc.returncode != 0:
        raise SecretManagerError(f"cannot add a version to {name} in {project}: {_err(proc)}")
    resource = proc.stdout.decode().strip()
    if not resource:
        raise SecretManagerError("gcloud added a version but did not print its name")
    return resource


def access(project: str, name: str, version: str, account: str | None) -> str:
    """The payload, in memory only. Callers must never print it."""
    proc = _run(
        ["secrets", "versions", "access", version.rsplit("/", 1)[-1],
         f"--secret={name}", f"--project={project}"],
        account,
    )
    if proc.returncode != 0:
        raise SecretManagerError(f"cannot read back {name} in {project}: {_err(proc)}")
    return proc.stdout.decode()


def matches(stored: str, value: str) -> bool:
    digest = lambda s: hashlib.sha256(s.encode()).digest()  # noqa: E731
    return digest(stored) == digest(value) or digest(stored.rstrip("\n")) == digest(value)
