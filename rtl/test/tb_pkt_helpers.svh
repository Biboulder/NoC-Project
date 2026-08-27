// Shared packet builders for the unit benches (tb_direction_decode, tb_router,
// tb_mesh). Header is {d1,d2,d3,d4} = 12 bits MSB-first; expect_pkt models the
// shift-left-3 per router hop (zero-fill tail, truncated to 12 bits).
function automatic packet_t make_packet(
    direction_e d1, direction_e d2, direction_e d3, direction_e d4,
    logic [31:0] payload
);
    logic [11:0] header;
    header = {d1, d2, d3, d4};
    make_packet = {header, payload};
endfunction

function automatic packet_t expect_pkt(
    direction_e d1, direction_e d2, direction_e d3, direction_e d4,
    logic [31:0] payload, int hops
);
    logic [11:0] header, shifted;
    header  = {d1, d2, d3, d4};
    shifted = (header << (3 * hops)) & 12'hFFF;
    expect_pkt = {shifted, payload};
endfunction
