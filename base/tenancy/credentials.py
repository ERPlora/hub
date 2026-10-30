"""The roles a hub's database is reached with, per cluster (round 2026-10-30, S2a; PLAN-DB §5 and §10; aws#23).

:func:`credentials_for` is the one place that says which user and password reach a hub's database, for one of two
roles: :data:`APP` (``hub_app``: a hub's alias, in the web and the worker) or :data:`MIGRATOR` (``hub_migrator``: its
``__ddl`` alias and the maintenance connection, ``base.tenancy.ops``, which only the worker and ``hub-migrate`` open).

- A hub on no cluster (``Hub.cluster`` empty: the settings' own server), or on a cluster without ``secret_name``: the
  environment's, the default connection's role for the app (``DB_USER``) and ``DB_MIGRATOR_USER`` for the migrator
  (the default connection's role where it is not set: local development, the tests).
- A cluster with ``secret_name``: its own, from the Secrets Manager secret of that role under that prefix,
  ``<secret_name>/app`` (``app_user``, ``app_password``) or ``<secret_name>/migrator`` (``migrator_user``,
  ``migrator_password``). The web's task role may read only ``…/app`` (aws#23), and only a migrator's connection asks
  for ``…/migrator``. Their ``host``, ``port``, ``pooler_host`` and ``pooler_port`` are not read: where the cluster is
  is its row's (``control.Cluster``), which the admin edits. Each secret is read once per :data:`SECRET_TTL_SECONDS`
  and kept in the process (a rotation reaches every task within that while); one that cannot be read, or is out of
  its shape, is :class:`CredentialsUnavailable` with its name and the reason, never the environment's roles in its
  place, and it is read again on the next call.

The passwords never show in a ``repr``.
"""

import json
import os
import threading
import time
from dataclasses import dataclass, field

from django.conf import settings

APP = "app"
MIGRATOR = "migrator"
#: What each role's secret must carry.
ROLE_KEYS = {APP: ("app_user", "app_password"), MIGRATOR: ("migrator_user", "migrator_password")}
#: How long a cluster's secret is kept in the process before it is read again.
SECRET_TTL_SECONDS = 600
#: The region of the secrets when the environment names none: ERPlora runs in Ireland (``base.storage``).
DEFAULT_REGION = "eu-west-1"

#: Monotonic seconds: the tests' clock replaces it.
_clock = time.monotonic
_cache: dict[str, tuple[float, "Credentials"]] = {}
_lock = threading.Lock()


class CredentialsUnavailable(RuntimeError):
    """A cluster's secret that could not be read or is out of shape: its name and why, never a password."""


@dataclass(frozen=True)
class Credentials:
    """One role's user and password on one cluster."""

    user: str
    password: str = field(repr=False)


def secrets_client():
    """Secrets Manager in the task's region, with the task role's credentials (the tests hand a fake instead)."""
    import boto3

    return boto3.client("secretsmanager", region_name=os.environ.get("AWS_REGION") or DEFAULT_REGION)


def environment_credentials(role: str) -> Credentials:
    """The environment's ``role``: the default connection's for the app, ``DB_MIGRATOR_USER``'s for the migrator."""
    default = settings.DATABASES["default"]
    if role == MIGRATOR and settings.DB_MIGRATOR_USER:
        return Credentials(user=settings.DB_MIGRATOR_USER, password=settings.DB_MIGRATOR_PASSWORD)
    return Credentials(user=default["USER"], password=default["PASSWORD"])


def credentials_for(cluster, role: str) -> Credentials:
    """``role``'s user and password on ``cluster`` (a ``control.Cluster``, or ``None`` for the settings' own)."""
    if role not in ROLE_KEYS:
        raise ValueError(f"No such role of a hub's database: {role!r} (only {', '.join(ROLE_KEYS)}).")
    prefix = getattr(cluster, "secret_name", "") if cluster is not None else ""
    if not prefix:
        return environment_credentials(role)
    secret_id = f"{prefix}/{role}"
    now = _clock()
    kept = _cache.get(secret_id)
    if kept is not None and kept[0] > now:
        return kept[1]
    found = _read(secret_id, ROLE_KEYS[role])
    with _lock:
        _cache[secret_id] = (now + SECRET_TTL_SECONDS, found)
    return found


def _read(secret_id: str, keys: tuple[str, str]) -> Credentials:
    try:
        answer = secrets_client().get_secret_value(SecretId=secret_id)
    except Exception as error:
        raise CredentialsUnavailable(
            f"The cluster's secret {secret_id!r} could not be read: {type(error).__name__}: {error}"
        ) from error
    try:
        values = json.loads(answer["SecretString"])
    except (KeyError, TypeError, ValueError) as error:
        raise CredentialsUnavailable(f"The cluster's secret {secret_id!r} is no JSON object.") from error
    if not isinstance(values, dict):
        raise CredentialsUnavailable(f"The cluster's secret {secret_id!r} is no JSON object.")
    missing = [key for key in keys if not isinstance(values.get(key), str) or not values[key]]
    if missing:
        raise CredentialsUnavailable(f"The cluster's secret {secret_id!r} lacks {', '.join(missing)}.")
    return Credentials(user=values[keys[0]], password=values[keys[1]])


def forget() -> None:
    """Drop every secret kept (the tests; a process reads them again on its next call)."""
    with _lock:
        _cache.clear()
