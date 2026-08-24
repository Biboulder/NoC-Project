# Edu4Chip_Router

## Running tests

Test benches run inside a Docker container with Icarus Verilog (`-g2012`):

```bash
./run_tb.sh direction_decode            # runs rtl/test/tb_direction_decode.sv
./run_tb.sh direction_decode --rebuild  # force a Docker image rebuild
```

Works on Linux and macOS with [Docker Desktop](https://www.docker.com/products/docker-desktop/);
the image is multi-arch, so both Intel and Apple Silicon are supported.
`run_tb.sh` needs bash (3.2+, bundled with macOS).

The `edu4chip-iverilog` image (see `Dockerfile`) is built automatically on
first use. All RTL in `rtl/` is compiled together with
`rtl/test/tb_<module>.sv`; package files (`*_pkg.sv`) are compiled first,
since iverilog requires definitions before imports. The repo is mounted
read-write, so test benches can write wave files (e.g. `$dumpfile`) into
`rtl/test/`.
