import struct

from facemesh_mouse.modules import cursor_image


def test_arrow_mask_tip_is_inside_and_far_corner_is_outside():
    mask = cursor_image._arrow_mask(32)
    assert mask.getpixel((0, 0)) == 255       # the tip, first polygon vertex
    assert mask.getpixel((31, 31)) == 0        # opposite corner, outside the silhouette


def test_contrast_outline_color_picks_black_on_a_light_fill():
    assert cursor_image._contrast_outline_color((255, 255, 255)) == (0, 0, 0)


def test_contrast_outline_color_picks_white_on_a_dark_fill():
    assert cursor_image._contrast_outline_color((0, 0, 0)) == (255, 255, 255)


def test_render_color_bitmap_is_transparent_outside_the_silhouette():
    image = cursor_image.render_color_bitmap(32, (255, 0, 0))
    assert image.getpixel((31, 31))[3] == 0


def test_render_color_bitmap_is_opaque_fill_color_in_the_shaft():
    image = cursor_image.render_color_bitmap(32, (255, 0, 0))
    r, g, b, a = image.getpixel((1, 5))
    assert a == 255
    assert (r, g, b) == (255, 0, 0)


def test_pack_1bpp_rows_pads_each_row_to_a_four_byte_boundary():
    # width=8 -> 1 real byte of bits + 3 bytes of padding per row
    packed = cursor_image._pack_1bpp_rows(8, lambda x, y: True)
    assert len(packed) == 8 * 4
    assert packed[0] == 0xFF
    assert packed[1:4] == b"\x00\x00\x00"


def test_pack_1bpp_rows_is_bottom_up():
    # Only the top row (y=0) is set; bottom-up storage puts it in the LAST row block.
    packed = cursor_image._pack_1bpp_rows(8, lambda x, y: y == 0)
    assert packed[-4] == 0xFF
    assert packed[0] == 0x00


def test_build_cur_bytes_color_has_a_cursor_type_icondir_header():
    image = cursor_image.render_color_bitmap(32, (0, 0, 0))
    data = cursor_image.build_cur_bytes_color(image)
    reserved, id_type, count = struct.unpack_from("<HHH", data, 0)
    assert (reserved, id_type, count) == (0, 2, 1)


def test_build_cur_bytes_color_entry_declares_32x32_and_32bpp():
    image = cursor_image.render_color_bitmap(32, (0, 0, 0))
    data = cursor_image.build_cur_bytes_color(image)
    width, height = struct.unpack_from("<BB", data, 6)
    assert (width, height) == (32, 32)
    bmi_offset = 6 + 16
    _size, _w, bi_height, _planes, bit_count = struct.unpack_from("<IiiHH", data, bmi_offset)
    assert bit_count == 32
    assert bi_height == 64  # 2x actual height (XOR + AND)


def test_build_cur_bytes_mista_is_1bpp_with_a_fully_set_and_mask():
    data = cursor_image.build_cur_bytes_mista(32)
    bmi_offset = 6 + 16
    _size, _w, _h, _planes, bit_count = struct.unpack_from("<IiiHH", data, bmi_offset)
    assert bit_count == 1
    xor_len = 32 * 4  # row_bytes(4) * 32 rows, 1bpp padded to a 4-byte boundary
    and_start = bmi_offset + 40 + 8 + xor_len  # header + 2-entry color table + xor mask
    assert data[and_start] == 0xFF
