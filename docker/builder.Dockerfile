# Context: an extracted native archive in tin/. See tools/ci/distribution_check.py.
FROM debian:bookworm-slim
ARG TIN_VERSION
LABEL org.opencontainers.image.title="Tin compiler" \
      org.opencontainers.image.source="https://github.com/yasserreslan/tin" \
      org.opencontainers.image.version="${TIN_VERSION}"
COPY tin/ /opt/tin/
ENV PATH="/opt/tin:/opt/tin/bin:${PATH}" TIN_ROOT="/opt/tin"
WORKDIR /src
ENTRYPOINT ["tin"]
CMD ["help"]
