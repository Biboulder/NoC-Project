"""Export a Schedule as a SystemVerilog include (``tb_schedule_pkg``).

The schedule-driven mesh bench (``rtl/test/tb_schedule.sv``) drives
injection purely from this table; the RTL contains no scheduling logic.
Directions are emitted as ``router_pkg::direction_e`` enum names, which
match the Python encodings exactly (verified against NSEW_packet.md).

Icarus Verilog 12 cannot elaborate unpacked-array ``localparam`` literals
(``'{}``), so each schedule "array" is emitted as a constant-returning
package function with one ``case`` arm per index -- same values, same
indexing, identical schedule data layout.
"""

from .header import Direction

__all__ = ["export_schedule"]

_MAX_HOPS = 4  # router_pkg HEADER=12 -> 4 direction fields (grids up to 3x3)


def _func(return_type, name, values, value_fmt):
    """One case-arm-per-index constant function over ``values``."""
    arms = "\n".join(
        f"      {i}: {name} = {value_fmt(v)};" for i, v in enumerate(values)
    )
    return (
        f"  function automatic {return_type} {name}(input int i);\n"
        f"    case (i)\n"
        f"{arms}\n"
        f"      default: {name} = {value_fmt(None)};\n"
        f"    endcase\n"
        f"  endfunction"
    )


def _int_fmt(v):
    return "-1" if v is None else str(v)


def _dir_fmt(v):
    return "LOCAL" if v is None else v.name


def export_schedule(schedule, source=None):
    """Return ``schedule`` as the text of a ``tb_schedule_pkg`` package."""
    n = schedule.grid
    assert n <= 3, "router_pkg HEADER=12 supports grids up to 3x3"
    if source is None:
        source = "<schedule>"

    # Rows sorted by (node, clock); alternatives keep file (row) order.
    rows = sorted(schedule.rows().items())
    row_keys = [key for key, _alts in rows]
    row_alts = [alts for _key, alts in rows]
    alts = [e for _key, row in rows for e in row]

    max_alts = max(len(a) for a in row_alts)
    max_clock = max(clock for _node, clock in row_keys)

    alt0 = []
    acc = 0
    for a in row_alts:
        alt0.append(acc)
        acc += len(a)
    nalt = [len(a) for a in row_alts]

    # Alternative routes as 4 direction fields, trailing LOCAL padding.
    dirs = []
    for e in alts:
        route = list(e.route) + [Direction.LOCAL] * (_MAX_HOPS - len(e.route))
        dirs.append([d for d in route])

    return "\n".join(
        [
            "// Schedule table for the mesh test bench (tb_schedule).",
            f"// Source: {source}",
            f"// grid {n}x{n}, frame {schedule.period} cycles, "
            f"{len(rows)} rows, {len(alts)} alternatives",
            "// Regenerate: python3 -m routing export-sv <schedule.sched> "
            "-o rtl/test/schedule_data.svh",
            "// Node/dest values are 0-based SV mesh indices (schedule labels - 1);",
            "// routes are zero-padded with LOCAL to 4 fields (router_pkg HEADER=12).",
            "// Each 'array' is a constant function (iverilog cannot elaborate",
            "// unpacked-array localparam literals); index i -> value i, as in",
            "// the source schedule.",
            "package tb_schedule_pkg;",
            "  import router_pkg::*;",
            "",
            f"  localparam int SCHED_GRID = {n};",
            f"  localparam int SCHED_FRAME = {schedule.period};",
            f"  localparam int SCHED_ROWS = {len(rows)};",
            f"  localparam int SCHED_ALTS = {len(alts)};",
            f"  localparam int SCHED_MAX_ALTS = {max_alts};",
            f"  localparam int SCHED_MAX_CLOCK = {max_clock};",
            "",
            _func("int", "SCHED_ROW_NODE", [node - 1 for node, _ in row_keys], _int_fmt),
            "",
            _func("int", "SCHED_ROW_CLOCK", [clock for _, clock in row_keys], _int_fmt),
            "",
            _func("int", "SCHED_ROW_ALT0", alt0, _int_fmt),
            "",
            _func("int", "SCHED_ROW_NALT", nalt, _int_fmt),
            "",
            _func("int", "SCHED_ALT_DST", [e.dest - 1 for e in alts], _int_fmt),
            "",
            _func("int", "SCHED_ALT_HOPS", [len(e.route) for e in alts], _int_fmt),
            "",
            _func("direction_e", "SCHED_ALT_D1", [d[0] for d in dirs], _dir_fmt),
            "",
            _func("direction_e", "SCHED_ALT_D2", [d[1] for d in dirs], _dir_fmt),
            "",
            _func("direction_e", "SCHED_ALT_D3", [d[2] for d in dirs], _dir_fmt),
            "",
            _func("direction_e", "SCHED_ALT_D4", [d[3] for d in dirs], _dir_fmt),
            "",
            "endpackage",
            "",
        ]
    )
