# ADR-129 native authorization probe. The executable enforces loopback, mTLS and disposable SQLite storage.
FROM golang:1.27.4-bookworm@sha256:4fa7c968ba93f1635670522dbb01a2c78150443e1385746924566079f36570ea AS builder
WORKDIR /src
ENV CGO_ENABLED=0 GOTOOLCHAIN=local GOWORK=off GOMAXPROCS=2

# Temporal v1.29.7, the exact source revision approved for the ADR-129 probe.
ADD --checksum=sha256:17f01fef5b9d8e3704cf6e660e997d3597451d53da2c8da2bfdf762a97a566c0 \
    https://codeload.github.com/temporalio/temporal/tar.gz/1f74f0c8e9935980d92a39069185671bbbba7c7e /tmp/temporal-source.tgz
COPY security-locks.patch /tmp/security-locks.patch
RUN test "$(go env GOVERSION)" = go1.27.4 \
 && tar -xzf /tmp/temporal-source.tgz --strip-components=1 \
 && printf '%s\n' \
      '94fc38124baa444db772f9db782099d3919db46209b2a06d09624a3b9ebdbaa9  go.mod' \
      'a1bfbb7684cbda89f97c26919bda1333f706ad9a1eb99b9e25b7c767ecd668a7  go.sum' > /tmp/expected-locks.sha256 \
 && sha256sum -c /tmp/expected-locks.sha256 \
 && cp go.mod security.mod && cp go.sum security.sum \
 && git apply --unidiff-zero --include=security.mod --include=security.sum /tmp/security-locks.patch \
 && printf '%s\n' \
      '6f9e12d6598f10e04e582ebdfce0f1548f2860b1edf9ff0902e9d758ee593eb0  security.mod' \
      'b73d5ea948305a52c4b1f9f105bce4418ead9b4ae88ba0f303c7200513fe2f0e  security.sum' >> /tmp/expected-locks.sha256 \
 && sha256sum -c /tmp/expected-locks.sha256
ENV GOFLAGS="-mod=readonly -modfile=/src/security.mod"
RUN go mod download && go mod verify && sha256sum -c /tmp/expected-locks.sha256

COPY assigned_completion.go assigned_completion_test.go assigned_failure.go assigned_failure_test.go assigned_poll.go assigned_start.go assigned_start_test.go \
     main.go main_test.go probe_main.go receipts.go reconciliation_describe.go /src/cmd/aires-auth-poc/
COPY Dockerfile .dockerignore security-locks.patch /tmp/build-inputs/

RUN --network=none \
    --mount=type=cache,target=/root/.cache/go-build \
    go test -p 2 -trimpath -count=1 ./cmd/aires-auth-poc \
 && mkdir /out \
 && go build -p 2 -trimpath -buildvcs=false -ldflags='-buildid=' -o /out/temporal-auth-poc ./cmd/aires-auth-poc \
 && go mod verify && sha256sum -c /tmp/expected-locks.sha256 \
 && sha256sum /src/cmd/aires-auth-poc/*.go /tmp/build-inputs/Dockerfile /tmp/build-inputs/.dockerignore /tmp/build-inputs/security-locks.patch > /out/extension.sha256 \
 && go version -m /out/temporal-auth-poc > /out/go-build-info.txt \
 && readelf -l /out/temporal-auth-poc > /out/elf-program-headers.txt \
 && if grep -q INTERP /out/elf-program-headers.txt; then exit 1; fi
WORKDIR /out
RUN sha256sum temporal-auth-poc > binary.sha256 \
 && printf '%s\n' 'temporal-probe:x:1000:1000:Temporal probe:/scratch:/nonexistent' > passwd \
 && printf '%s\n' 'temporal-probe:x:1000:' > group

FROM scratch AS sqlite-probe
LABEL org.opencontainers.image.source="https://github.com/F4nin/AI-RES" \
      io.ai-res.temporal.upstream.source="https://github.com/temporalio/temporal" \
      io.ai-res.temporal.upstream.revision="1f74f0c8e9935980d92a39069185671bbbba7c7e" \
      io.ai-res.build.context="infra/temporal_auth_poc" \
      org.opencontainers.image.version="1.29.7" \
      org.opencontainers.image.title="AI RES isolated Temporal authorization probe"
COPY --from=builder /out/temporal-auth-poc /temporal-auth-poc
COPY --from=builder /out/passwd /etc/passwd
COPY --from=builder /out/group /etc/group
COPY --from=builder /out/extension.sha256 /out/go-build-info.txt /out/elf-program-headers.txt /out/binary.sha256 /provenance/
COPY --from=builder /tmp/expected-locks.sha256 /src/LICENSE /provenance/
WORKDIR /scratch
USER 1000:1000
ENTRYPOINT ["/temporal-auth-poc"]

FROM builder AS postgres-test-builder
COPY postgres_probe_test.go /src/cmd/aires-auth-poc/
WORKDIR /src
RUN --network=none \
    --mount=type=cache,target=/root/.cache/go-build \
    go test -p 2 -trimpath -count=1 -tags temporal_postgres_probe ./cmd/aires-auth-poc \
 && go test -p 2 -trimpath -buildvcs=false -ldflags='-buildid=' -tags temporal_postgres_probe -c \
        -o /out/temporal-postgres-test ./cmd/aires-auth-poc \
 && go mod verify && sha256sum -c /tmp/expected-locks.sha256

FROM scratch AS postgres-test
COPY --from=postgres-test-builder /out/temporal-postgres-test /temporal-postgres-test
COPY --from=builder /out/passwd /etc/passwd
COPY --from=builder /out/group /etc/group
WORKDIR /scratch
USER 1000:1000
ENTRYPOINT ["/temporal-postgres-test", "-test.run=^TestServeNativePostgresProbe$"]

FROM builder AS runtime-builder
COPY runtime_main.go runtime_main_test.go /src/cmd/aires-auth-poc/
WORKDIR /src
RUN --network=none \
    --mount=type=cache,target=/root/.cache/go-build \
    go test -p 2 -trimpath -count=1 -tags temporal_runtime ./cmd/aires-auth-poc \
 && go build -p 2 -tags temporal_runtime -trimpath -buildvcs=false -ldflags='-buildid=' \
        -o /out/temporal-native ./cmd/aires-auth-poc \
 && go mod verify && sha256sum -c /tmp/expected-locks.sha256 \
 && sha256sum /src/cmd/aires-auth-poc/*.go /tmp/build-inputs/Dockerfile /tmp/build-inputs/.dockerignore /tmp/build-inputs/security-locks.patch > /out/runtime-extension.sha256 \
 && go version -m /out/temporal-native > /out/runtime-go-build-info.txt \
 && readelf -l /out/temporal-native > /out/runtime-elf-program-headers.txt \
 && if grep -q INTERP /out/runtime-elf-program-headers.txt; then exit 1; fi
WORKDIR /out
RUN sha256sum temporal-native > runtime-binary.sha256

FROM scratch AS native-runtime
LABEL org.opencontainers.image.source="https://github.com/F4nin/AI-RES" \
      io.ai-res.temporal.upstream.source="https://github.com/temporalio/temporal" \
      io.ai-res.temporal.upstream.revision="1f74f0c8e9935980d92a39069185671bbbba7c7e" \
      io.ai-res.build.context="infra/temporal_auth_poc" \
      org.opencontainers.image.version="1.29.7" \
      org.opencontainers.image.title="AI RES native Temporal server"
COPY --from=runtime-builder /out/temporal-native /temporal-native
COPY --from=builder /out/passwd /etc/passwd
COPY --from=builder /out/group /etc/group
COPY --from=runtime-builder /out/runtime-*.sha256 /out/runtime-*.txt /tmp/expected-locks.sha256 /src/LICENSE /provenance/
USER 1000:1000
ENTRYPOINT ["/temporal-native"]

FROM sqlite-probe AS default
