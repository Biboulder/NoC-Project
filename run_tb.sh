#!/usr/bin/env bash
#
# Run Icarus Verilog test benches for an RTL module inside Docker.
#
# Usage: ./run_tb.sh <module> [--rebuild]
#
# Compiles all RTL sources in rtl/ together with rtl/test/tb_<module>.sv
# inside the edu4chip-iverilog Docker image and runs the simulation.
# The image is built automatically on first use.
set -euo pipefail

IMAGE="edu4chip-iverilog"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<'EOF'
Usage: run_tb.sh <module> [--rebuild]

Run the test bench rtl/test/tb_<module>.sv against the RTL in rtl/.

  <module>    RTL module name; the test bench must be rtl/test/tb_<module>.sv
  --rebuild   force a rebuild of the Docker image

The repo is mounted read-write into the container, so test benches can
write wave files (e.g. $dumpfile) into rtl/test/.
EOF
}

MODULE="${1:-}"
if [[ -z "${MODULE}" || "${MODULE}" == "-h" || "${MODULE}" == "--help" ]]; then
    usage
    exit 1
fi

if [[ ! "${MODULE}" =~ ^[A-Za-z0-9_]+$ ]]; then
    echo "error: module name must contain only letters, digits, underscores" >&2
    exit 1
fi

TB="rtl/test/tb_${MODULE}.sv"
if [[ ! -f "${ROOT}/${TB}" ]]; then
    echo "error: no test bench found at ${TB}" >&2
    exit 1
fi

if [[ "${2:-}" == "--rebuild" ]] || ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
    echo "building ${IMAGE} image..."
    docker build -t "${IMAGE}" "${ROOT}"
fi

echo "compiling and running ${TB}..."
exec docker run -i --rm \
    -v "${ROOT}:/work:rw" \
    -w /work \
    -e TB="${TB}" \
    "${IMAGE}" \
    sh -s <<'EOF'
set -e
pkgs=""
rest=""
for f in rtl/*.sv; do
    case "$f" in
        *_pkg.sv) pkgs="$pkgs $f" ;;   # packages first: iverilog needs them before imports
        *)        rest="$rest $f" ;;
    esac
done
iverilog -g2012 -o /tmp/sim.out $pkgs $rest "$TB"
vvp /tmp/sim.out
EOF
