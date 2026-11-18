# ADR135 inference-only candidate; never retags the official image or product stack.
FROM golang:1.27.4-bookworm@sha256:4fa7c968ba93f1635670522dbb01a2c78150443e1385746924566079f36570ea AS builder
WORKDIR /src
ENV CGO_ENABLED=1 GOTOOLCHAIN=local GOWORK=/src/go.work GOFLAGS=-mod=readonly GOMAXPROCS=2
COPY source/core ./core
COPY source/transports ./transports
COPY go.work expected-locks.sha256 ./
COPY headless-index.html ./transports/bifrost-http/ui/index.html
RUN test "$(go env GOVERSION)" = go1.27.4 && sha256sum -c expected-locks.sha256
RUN mkdir /out && cd transports \
 && test "$(go list -m -f '{{.Dir}}' github.com/maximhq/bifrost/core)" = /src/core \
 && go list -m -json github.com/maximhq/bifrost/core > /out/local-core.json \
 && go build -p 2 -trimpath -buildvcs=false -tags sqlite_static,netgo \
      -ldflags="-w -s -X main.Version=v2.5.1-candidate-fingerprint -extldflags '-static'" \
      -o /out/main ./bifrost-http \
 && cd /src && sha256sum -c expected-locks.sha256 \
 && go version -m /out/main > /out/go-build-info.txt \
 && readelf -l /out/main > /out/elf-program-headers.txt \
 && if grep -q INTERP /out/elf-program-headers.txt; then exit 1; fi \
 && cd /out && sha256sum main > binary.sha256

# Keep pinned CA/system/entrypoint/user configuration; replace only the binary.
FROM maximhq/bifrost:v2.5.1@sha256:5ec9873acaf1687556b6e4dd854b92b539d9debf87a5a683b66338648b84d3c8 AS runtime
COPY --from=builder /out/main /app/main
COPY --from=builder /out/local-core.json /out/go-build-info.txt /out/elf-program-headers.txt /out/binary.sha256 /app/candidate-provenance/
COPY source/LICENSE /app/candidate-provenance/LICENSE
COPY manifest.json /app/candidate-provenance/source-manifest.json
