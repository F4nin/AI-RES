"""Configure the test-only Temporal Postgres/mTLS profile against a disposable database."""
import datetime as dt
import socket
import ssl
import subprocess
from pathlib import Path
from secrets import token_hex

import psycopg
import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, generate_private_key
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from psycopg import sql

_SERVER_NAME = "temporal-probe-internode"
DATABASES = {"default": "temporal_probe_history", "visibility": "temporal_probe_visibility"}
COMPOSE_DATABASES = {"default": "temporal_db", "visibility": "temporal_visibility_db"}
COMPOSE_CA = Path("/run/secrets/postgres_tls_ca_cert")


def _internode_certificates(root: Path, *, server_name: str = _SERVER_NAME) -> None:
    now = dt.datetime.now(dt.UTC)
    ca_key, leaf_key = generate_private_key(SECP256R1()), generate_private_key(SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Temporal test internode CA")])
    leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, server_name)])

    def certificate(subject, key):
        return (x509.CertificateBuilder().subject_name(subject).issuer_name(ca_name).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(minutes=1))
                .not_valid_after(now + dt.timedelta(hours=1)))

    ca = (certificate(ca_name, ca_key).add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False, data_encipherment=False,
                                       key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
          .sign(ca_key, hashes.SHA256()))
    leaf = (certificate(leaf_name, leaf_key).add_extension(x509.SubjectAlternativeName([x509.DNSName(server_name)]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]), critical=True)
            .sign(ca_key, hashes.SHA256()))
    (root / "internode-ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    (root / "internode.pem").write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    key_path = root / "internode.key"
    key_path.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    key_path.chmod(0o600)


def configure_postgres(root: Path, connection: psycopg.Connection, port: int, schema_tool: Path, schema_root: Path) -> tuple[int, int]:
    """Create two fixture databases in the test cluster, then amend the generated loopback configuration."""
    if connection.info.host not in {"127.0.0.1", "localhost"} or connection.info.port != port:
        raise ValueError("the PostgreSQL probe requires a loopback test cluster")
    password = token_hex(24)
    connection.execute(sql.SQL("CREATE ROLE temporal_probe LOGIN PASSWORD {}").format(sql.Literal(password)))
    for name, schema in zip(DATABASES.values(), ("temporal", "visibility"), strict=True):
        connection.execute(sql.SQL("CREATE DATABASE {} OWNER temporal_probe").format(sql.Identifier(name)))
        command = [str(schema_tool), "--plugin", "postgres12", "--ep", "127.0.0.1", "-p", str(port), "-u", "temporal_probe", "--db", name]
        for arguments in (("setup-schema", "-v", "0.0"), ("update-schema", "-d", str(schema_root / schema / "versioned"))):
            result = subprocess.run(command + list(arguments), env={"SQL_PASSWORD": password}, capture_output=True, timeout=60, check=False)  # noqa: S603
            if result.returncode != 0:
                raise RuntimeError(f"Temporal {schema} fixture schema {arguments[0]} failed with exit {result.returncode}")
    return write_postgres_configuration(root, port, password)


def write_postgres_configuration(root: Path, port: int, password: str, *, candidate: bool = False) -> tuple[int, int]:
    _internode_certificates(root)
    config_path = root / "poc.yaml"
    config = yaml.safe_load(config_path.read_text())
    databases = COMPOSE_DATABASES if candidate else DATABASES
    host, user = ("postgres", "temporal") if candidate else ("127.0.0.1", "temporal_probe")
    stores = {}
    for store, name in databases.items():
        sql_config = {"pluginName": "postgres12", "databaseName": name, "user": user, "password": password,
                      "connectAddr": f"{host}:{port}", "connectProtocol": "tcp", "maxConns": 4, "maxIdleConns": 2}
        if candidate:
            sql_config["tls"] = {"enabled": True, "enableHostVerification": True, "caFile": str(COMPOSE_CA), "serverName": "postgres"}
        stores[store] = {"sql": sql_config}
    config["persistence"]["datastores"] = stores
    config["global"]["tls"]["internode"] = {
        "server": {"certFile": str(root / "internode.pem"), "keyFile": str(root / "internode.key"),
                   "requireClientAuth": True, "clientCaFiles": [str(root / "internode-ca.pem")]},
        "client": {"serverName": _SERVER_NAME, "rootCaFiles": [str(root / "internode-ca.pem")]},
    }
    config_path.chmod(0o600)
    config_path.write_text(yaml.safe_dump(config))
    return (config["services"]["history"]["rpc"]["grpcPort"], config["services"]["matching"]["rpc"]["grpcPort"])


def probe_internode_tls(root: Path, port: int, identity: str | None) -> None:
    """Test an internode gRPC listener's certificate negotiation over loopback."""
    context = ssl.create_default_context(cafile=root / "internode-ca.pem")
    context.maximum_version = ssl.TLSVersion.TLSv1_2  # the client receives the certificate rejection during the handshake
    if identity is not None:
        context.load_cert_chain(root / f"{identity}.pem", root / f"{identity}.key")
    with socket.create_connection(("127.0.0.1", port), timeout=2) as raw, context.wrap_socket(raw, server_hostname=_SERVER_NAME):
        pass
