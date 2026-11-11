# MinIO server and mc client built from pinned source tags (the upstream community images are no longer published; owner decision S03).
# Both git tags are verified against pinned commit SHAs before building. AGPL-3.0 components: license review at release (DOC-015 §14).
FROM golang:1.27.4-bookworm@sha256:4fa7c968ba93f1635670522dbb01a2c78150443e1385746924566079f36570ea AS build
ARG MINIO_TAG=RELEASE.2025-10-15T17-29-55Z
ARG MINIO_COMMIT=9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a
ARG MC_TAG=RELEASE.2025-08-13T08-35-41Z
ARG MC_COMMIT=7394ce0dd2a80935aded936b09fa12cbb3cb8096
# Minimum fixed versions of vulnerable transitive dependencies reported by the image scan (Trivy HIGH/CRITICAL, fix available upstream);
# the pinned upstream release tags predate them. Per-tree lists: `go get` of a module a tree does not use would ADD it. The runtime suite
# (bucket create + versioning via mc against minio) exercises the result. Findings without a fix stay in vulnerability-exceptions.yaml.
ARG MINIO_DEP_FIXES="golang.org/x/net@v0.62.0 golang.org/x/crypto@v0.58.0 github.com/klauspost/compress@v1.18.7 google.golang.org/grpc@v1.83.2 github.com/rabbitmq/amqp091-go@v1.13.0 github.com/apache/thrift@v0.24.0 github.com/buger/jsonparser@v1.1.2 github.com/go-jose/go-jose/v4@v4.1.6 go.opentelemetry.io/otel/sdk@v1.44.0"
ARG MC_DEP_FIXES="golang.org/x/net@v0.62.0 golang.org/x/crypto@v0.58.0 github.com/klauspost/compress@v1.18.7 google.golang.org/grpc@v1.83.2"
ENV CGO_ENABLED=0 GOFLAGS=-trimpath
# Network steps (git clone, module download, checksum-database lookups) are retried a bounded number of times: a transient failure of an external
# service (e.g. sum.golang.org `stream error: INTERNAL_ERROR`, S05 CI run 43029232241) must not fail the build. Verification stays ON (GOSUMDB is not
# disabled) and every clone is still checked against the pinned commit, so a retry can only repeat the same verified work.
RUN set -eux; \
    retry() { n=1; until "$@"; do [ "$n" -ge 4 ] && return 1; echo "retry $n/3: $*" >&2; n=$((n + 1)); sleep $((n * 5)); done; }; \
    retry sh -c 'rm -rf /src/minio && git clone --depth 1 --branch "$1" https://github.com/minio/minio /src/minio' _ "$MINIO_TAG"; \
    test "$(git -C /src/minio rev-parse 'HEAD^{commit}')" = "$MINIO_COMMIT"; \
    retry sh -c 'rm -rf /src/mc && git clone --depth 1 --branch "$1" https://github.com/minio/mc /src/mc' _ "$MC_TAG"; \
    test "$(git -C /src/mc rev-parse 'HEAD^{commit}')" = "$MC_COMMIT"; \
    cd /src/minio; \
    retry go get $MINIO_DEP_FIXES; \
    retry go build -ldflags "-s -w" -o /out/minio .; \
    cd /src/mc; \
    retry go get $MC_DEP_FIXES; \
    retry go build -ldflags "-s -w" -o /out/mc .; \
    test -x /out/minio && test -x /out/mc

FROM debian:bookworm-slim@sha256:734a72b3d6142a71993b4bc580ca01d8ca687f77a2c422d96a961d3376b179bc AS base
RUN groupadd --gid 10002 minio && useradd --uid 10002 --gid 10002 --no-create-home --shell /usr/sbin/nologin minio

FROM base AS minio
COPY --from=build /out/minio /usr/local/bin/minio
# Named volumes inherit ownership from the image path: /data must belong to the runtime user.
RUN mkdir /data && chown 10002:10002 /data
USER 10002:10002
ENTRYPOINT ["/usr/local/bin/minio"]

FROM base AS mc
COPY --from=build /out/mc /usr/local/bin/mc
USER 10002:10002
ENTRYPOINT ["/usr/local/bin/mc"]
