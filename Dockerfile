# Icarus Verilog toolchain for Edu4Chip router test benches.
# Pinned to Debian trixie (iverilog 12.0, SystemVerilog via -g2012).
FROM debian:trixie-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends iverilog \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
CMD ["iverilog", "-g2012"]
