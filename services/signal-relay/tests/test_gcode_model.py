import pytest

from signal_relay import gcode_model
from signal_relay.gcode_model import ModelRejected, parse_gcode, started_layer_count

# Two layers. Layer 1 has an outer wall loop and an inner wall that must not be drawn.
BASE = (
    "G90\n"
    ";LAYER_CHANGE\n"
    ";Z:0.2\n"
    ";HEIGHT:0.2\n"
    "G1 X0 Y0 Z0.2 F600\n"
    ";TYPE:Outer wall\n"
    "G1 X10 Y0 E1\n"
    "G1 X10 Y10 E2\n"
    "G1 X0 Y10 E3\n"
    "G1 X0 Y0 E4\n"
    ";TYPE:Inner wall\n"
    "G1 X5 Y5 E5\n"
    ";LAYER_CHANGE\n"
    ";Z:0.4\n"
    ";HEIGHT:0.2\n"
    "G1 X0 Y0 Z0.4\n"
    ";TYPE:Outer wall\n"
    "G1 X10 Y0 E6\n"
)


def _parse(text: str, chunk_size: int | None = None):
    data = text.encode()
    if chunk_size is None:
        chunks = [data]
    else:
        chunks = [data[index:index + chunk_size] for index in range(0, len(data), chunk_size)]
    return parse_gcode(chunks)


def _byte_offsets(text: str, marker: str) -> list[int]:
    data = text.encode()
    found = []
    start = 0
    while (index := data.find(marker.encode(), start)) >= 0:
        found.append(index)
        start = index + 1
    return found


def _paths(text: str, layer: int = 0) -> list[list[int]]:
    return _parse(text).payload["layers"][layer]["paths"]


def test_records_the_byte_offset_height_and_z_of_each_layer_change():
    model = _parse(BASE)

    assert model.layer_offsets == tuple(_byte_offsets(BASE, ";LAYER_CHANGE"))
    assert model.layer_zs == (0.2, 0.4)
    assert model.payload["layerCount"] == 2
    assert model.payload["layerHeight"] == 0.2
    assert [layer["z"] for layer in model.payload["layers"]] == [0.2, 0.4]


def test_draws_only_outer_wall_extrusion_as_quantized_polylines():
    layers = _parse(BASE).payload["layers"]

    # The outer loop keeps its corners; the inner wall and the travel move are not drawn.
    assert layers[0]["paths"] == [[0, 0, 100, 0, 100, 100, 0, 100, 0, 0]]
    assert layers[1]["paths"] == [[0, 0, 100, 0]]


def test_bounding_box_is_reported_in_millimetres_over_the_drawn_paths():
    assert _parse(BASE).payload["bbox"] == {"minX": 0.0, "minY": 0.0, "maxX": 10.0, "maxY": 10.0}


def test_relative_extrusion_m83_draws_only_positive_extrusion():
    text = (
        "M83\nG90\n;LAYER_CHANGE\nG1 X0 Y0\n;TYPE:Outer wall\n"
        "G1 X10 Y0 E1\nG1 X20 Y0 E-0.5\nG1 X30 Y0 E1\n"
    )

    assert _paths(text) == [[0, 0, 100, 0], [200, 0, 300, 0]]


def test_absolute_extrusion_m82_treats_a_lower_e_value_as_retraction():
    text = (
        "M82\nG90\n;LAYER_CHANGE\nG1 X0 Y0\n;TYPE:Outer wall\n"
        "G1 X10 Y0 E1\nG1 X20 Y0 E0.5\nG1 X30 Y0 E2\n"
    )

    assert _paths(text) == [[0, 0, 100, 0], [200, 0, 300, 0]]


def test_relative_positioning_g91_applies_to_xy_moves_and_collinear_points_are_dropped():
    text = ";LAYER_CHANGE\nG90\nG1 X0 Y0\n;TYPE:Outer wall\nG91\nG1 X5 Y0 E1\nG1 X5 Y0 E2\n"

    assert _paths(text) == [[0, 0, 100, 0]]


def test_travel_moves_split_polylines_and_are_never_drawn():
    text = ";LAYER_CHANGE\nG1 X0 Y0\n;TYPE:Outer wall\nG1 X10 Y0 E1\nG1 X20 Y0\nG1 X30 Y0 E2\n"

    assert _paths(text) == [[0, 0, 100, 0], [200, 0, 300, 0]]


def test_positions_are_quantized_to_tenth_millimetres_and_repeated_points_are_dropped():
    text = ";LAYER_CHANGE\nG1 X0.04 Y0\n;TYPE:Outer wall\nG1 X10.06 Y0.14 E1\nG1 X10.06 Y0.14 E2\n"

    assert _paths(text) == [[0, 0, 101, 1]]


def test_douglas_peucker_drops_a_point_within_two_tenths_of_a_millimetre_and_keeps_a_deeper_one():
    shallow = ";LAYER_CHANGE\nG1 X0 Y0\n;TYPE:Outer wall\nG1 X5 Y0.1 E1\nG1 X10 Y0 E2\n"
    deep = ";LAYER_CHANGE\nG1 X0 Y0\n;TYPE:Outer wall\nG1 X5 Y0.3 E1\nG1 X10 Y0 E2\n"

    assert _paths(shallow) == [[0, 0, 100, 0]]
    assert _paths(deep) == [[0, 0, 50, 3, 100, 0]]


def test_arc_moves_keep_the_position_on_their_endpoint_and_are_drawn_as_chords():
    text = ";LAYER_CHANGE\nG1 X0 Y0\n;TYPE:Outer wall\nG2 X10 Y10 I5 J5 E1\nG1 X20 Y10 E2\n"

    assert _paths(text) == [[0, 0, 100, 100, 200, 100]]


def test_moves_without_a_known_start_position_are_not_drawn():
    text = ";LAYER_CHANGE\nG28\n;TYPE:Outer wall\nG1 X10 Y0 E1\nG1 X20 Y0 E2\n"

    assert _paths(text) == [[100, 0, 200, 0]]


def test_line_numbers_and_trailing_comments_are_ignored():
    text = ";LAYER_CHANGE\nN10 G1 X0 Y0 ; travel\n;TYPE:Outer wall\nN11 G1 X10 Y0 E1 ; draw\n"

    assert _paths(text) == [[0, 0, 100, 0]]


def test_prusa_external_perimeter_counts_as_outer_wall_and_other_types_end_the_section():
    text = (
        ";LAYER_CHANGE\nG1 X0 Y0\n;TYPE:External perimeter\nG1 X10 Y0 E1\n"
        ";TYPE:Internal perimeter\nG1 X20 Y0 E2\n"
    )

    assert _paths(text) == [[0, 0, 100, 0]]


def test_crlf_line_endings_count_toward_the_byte_offsets():
    text = BASE.replace("\n", "\r\n")
    model = _parse(text)

    assert model.layer_offsets == tuple(_byte_offsets(text, ";LAYER_CHANGE"))
    assert model.payload["layers"][0]["paths"] == [[0, 0, 100, 0, 100, 100, 0, 100, 0, 0]]


def test_streaming_one_byte_at_a_time_gives_the_same_model():
    assert _parse(BASE, chunk_size=1) == _parse(BASE)


def test_layer_height_falls_back_to_the_positive_z_steps_when_no_height_marker_exists():
    text = ";LAYER_CHANGE\n;Z:0.3\nG1 X0 Y0\n;LAYER_CHANGE\n;Z:0.6\n"

    assert _parse(text).payload["layerHeight"] == 0.3


def test_most_common_height_marker_wins():
    text = (
        ";LAYER_CHANGE\n;Z:0.3\n;HEIGHT:0.3\n"
        ";LAYER_CHANGE\n;Z:0.5\n;HEIGHT:0.2\n"
        ";LAYER_CHANGE\n;Z:0.7\n;HEIGHT:0.2\n"
    )

    assert _parse(text).payload["layerHeight"] == 0.2


def test_started_layer_count_counts_layer_changes_at_or_before_the_position():
    offsets = (100, 300, 500)

    assert started_layer_count(offsets, 0) == 0
    assert started_layer_count(offsets, 100) == 1
    assert started_layer_count(offsets, 299) == 1
    assert started_layer_count(offsets, 300) == 2
    assert started_layer_count(offsets, 10_000) == 3


def test_point_cap_escalates_the_tolerance_until_the_path_fits(monkeypatch):
    # Every odd point sits 0.3 mm (3 units) off the chord: kept at the 0.2 mm tolerance, dropped at 0.4 mm.
    monkeypatch.setattr(gcode_model, "MAX_POINTS", 10)
    text = ";LAYER_CHANGE\nG1 X0 Y0\n;TYPE:Outer wall\n" + "".join(
        f"G1 X{index} Y{0.3 * (index % 2):g} E{index}\n" for index in range(1, 41)
    )

    assert _paths(text) == [[0, 0, 400, 0]]


def test_a_model_that_cannot_fit_the_point_cap_is_rejected(monkeypatch):
    monkeypatch.setattr(gcode_model, "MAX_POINTS", 1)

    with pytest.raises(ModelRejected, match="too_many_points"):
        _parse(BASE)


def test_a_model_that_cannot_fit_the_json_cap_is_rejected(monkeypatch):
    monkeypatch.setattr(gcode_model, "MAX_JSON_BYTES", 10)

    with pytest.raises(ModelRejected, match="model_too_large"):
        _parse(BASE)


def test_more_layers_than_the_cap_are_rejected(monkeypatch):
    monkeypatch.setattr(gcode_model, "MAX_LAYERS", 1)

    with pytest.raises(ModelRejected, match="too_many_layers"):
        _parse(BASE)


def test_an_overlong_line_is_rejected_instead_of_being_buffered(monkeypatch):
    monkeypatch.setattr(gcode_model, "MAX_LINE_BYTES", 16)

    with pytest.raises(ModelRejected, match="line_too_long"):
        _parse(";LAYER_CHANGE\n" + "G1 X1 " * 10 + "\n")


@pytest.mark.parametrize("coordinate", ["300000000", "-300000000", "1e9"])
def test_a_coordinate_outside_any_printable_range_is_refused_not_crashed(coordinate):
    text = (
        ";LAYER_CHANGE\n;Z:0.2\n;HEIGHT:0.2\n;TYPE:Outer wall\n"
        f"G1 X{coordinate} Y0 E1\nG1 X0 Y0 E2\n;TYPE:Inner wall\n"
    )

    with pytest.raises(ModelRejected):
        _parse(text)
