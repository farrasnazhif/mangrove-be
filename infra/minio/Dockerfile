# Build the official source release containing the October 2025 security fix.
# https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z
FROM golang:1.24-bookworm AS build
RUN CGO_ENABLED=0 go install github.com/minio/minio@RELEASE.2025-10-15T17-29-55Z

FROM debian:bookworm-slim
COPY --from=build /go/bin/minio /usr/local/bin/minio
COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
RUN mkdir /data && chown 10001:10001 /data
USER 10001:10001
WORKDIR /data
EXPOSE 9000 9001
ENTRYPOINT ["/usr/local/bin/minio"]
