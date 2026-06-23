import os
import struct
import zlib
import io
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from PIL import Image


PNG_SIG = b'\x89PNG\r\n\x1a\n'


@dataclass
class TextChunk:
    keyword: str
    text: str


@dataclass
class SaveFile:
    path: str
    metadata: dict[str, str] = field(default_factory=dict)
    save_version: int = 0
    save_prod_version: int = 0
    screenshot: Optional[Image.Image] = None
    rng_data: bytes = b''
    snap_compressed: bytes = b''
    snap_decompressed: Optional[bytes] = None
    raw_chunks: list[tuple[str, bytes]] = field(default_factory=list)


def _read_png_chunks(path: str) -> list[tuple[str, bytes, int]]:
    chunks = []
    with open(path, 'rb') as f:
        sig = f.read(8)
        if sig != PNG_SIG:
            raise ValueError("Not a valid PNG file")

        while True:
            length_bytes = f.read(4)
            if not length_bytes or len(length_bytes) < 4:
                break
            length = struct.unpack('>I', length_bytes)[0]
            chunk_type = f.read(4).decode('latin-1')
            chunk_data = f.read(length)
            f.read(4)  # skip CRC
            chunks.append((chunk_type, chunk_data, length))
            if chunk_type == 'IEND':
                break

    return chunks


def resolve_save_path(path: str) -> str:
    p = path.strip().strip('"\'')
    p = os.path.expanduser(p)
    p = os.path.expandvars(p)
    p = os.path.abspath(p)
    if not os.path.isfile(p):
        raise FileNotFoundError(f"Save file not found: {p}")
    return p


def parse_save(path: str) -> SaveFile:
    path = resolve_save_path(path)
    sf = SaveFile(path=path)

    with open(path, 'rb') as f:
        all_data = f.read()

    pos = 8
    palette_data = None
    idat_chunks = []
    width = height = 0
    bit_depth = color_type = 0

    while pos < len(all_data):
        length = struct.unpack('>I', all_data[pos:pos+4])[0]
        chunk_type = all_data[pos+4:pos+8].decode('latin-1')
        chunk_data = all_data[pos+8:pos+8+length]
        pos += 4 + 4 + length + 4

        sf.raw_chunks.append((chunk_type, chunk_data))

        if chunk_type == 'IHDR':
            width = struct.unpack('>I', chunk_data[0:4])[0]
            height = struct.unpack('>I', chunk_data[4:8])[0]
            bit_depth = chunk_data[8]
            color_type = chunk_data[9]

        elif chunk_type == 'PLTE':
            palette_data = chunk_data

        elif chunk_type == 'IDAT':
            idat_chunks.append(chunk_data)

        elif chunk_type == 'tEXt':
            null_pos = chunk_data.index(0)
            key = chunk_data[:null_pos].decode('latin-1')
            val = chunk_data[null_pos+1:].decode('latin-1').strip()
            sf.metadata[key] = val

        elif chunk_type == 'raNd':
            sf.rng_data = chunk_data

        elif chunk_type == 'snAp':
            sf.snap_compressed = chunk_data

        if chunk_type == 'IEND':
            break

    # Parse save version from metadata
    if 'ECWolf Save Version' in sf.metadata:
        sig = sf.metadata['ECWolf Save Version']
        sf.save_version = int(sig[10:].rstrip('ull'))
    if 'ECWolf Save Product Version' in sf.metadata:
        sf.save_prod_version = int(sf.metadata['ECWolf Save Product Version'])

    # Decompress snAp
    if sf.snap_compressed:
        sf.snap_decompressed = _decompress_snap(sf.snap_compressed)

    # Decode screenshot
    if palette_data and idat_chunks and width and height:
        sf.screenshot = _decode_screenshot(
            idat_chunks, palette_data, width, height, bit_depth, color_type
        )

    return sf


def _decompress_snap(data: bytes) -> Optional[bytes]:
    if len(data) < 12:
        return None
    sig = data[:4]
    if sig != b'FLZL':
        return None
    comp_size = struct.unpack('>I', data[4:8])[0]
    uncomp_size = struct.unpack('>I', data[8:12])[0]
    compressed = data[12:]
    if comp_size == 0:
        return compressed[:uncomp_size]
    try:
        return zlib.decompress(compressed)
    except zlib.error:
        return None


def _compress_snap(data: bytes, original: bytes) -> bytes:
    if len(data) < 12:
        return original
    header = original[:12]
    compressed = zlib.compress(data)
    if len(compressed) > 0xFFFFFFFF:
        return original
    header = struct.pack('>I', len(data))  # uncomp_size in header
    # Original FLZL header: sig(4) + comp_size(4) + uncomp_size(4)
    sig = original[:4]
    new_header = sig + struct.pack('>I', len(compressed)) + struct.pack('>I', len(data))
    return new_header + compressed


def _decode_screenshot(
    idat_chunks: list[bytes],
    palette_data: bytes,
    width: int,
    height: int,
    bit_depth: int,
    color_type: int,
) -> Optional[Image.Image]:
    try:
        raw = b''.join(idat_chunks)
        decompressed = zlib.decompress(raw)
        if color_type == 3 and bit_depth == 8:
            # PNG raw data has 1 filter byte per row; strip them
            stride = width + 1
            pixels = bytearray()
            for row in range(height):
                off = row * stride
                fb = decompressed[off]
                row_data = decompressed[off + 1 : off + 1 + width]
                if fb == 1:  # Sub
                    prev = 0
                    for b in row_data:
                        v = (b + prev) & 0xFF
                        pixels.append(v)
                        prev = v
                elif fb == 2:  # Up
                    for i, b in enumerate(row_data):
                        above = pixels[(row - 1) * width + i] if row > 0 else 0
                        pixels.append((b + above) & 0xFF)
                else:  # 0 = None (most common in ECWolf saves)
                    pixels.extend(row_data)

            img = Image.frombytes('P', (width, height), bytes(pixels))
            img.putpalette(palette_data)
            return img.convert('RGBA')
        else:
            return None
    except Exception:
        return None


def rebuild_save_file(sf: SaveFile, new_metadata: Optional[dict[str, str]] = None, new_snap: Optional[bytes] = None) -> bytes:
    buf = io.BytesIO()
    buf.write(PNG_SIG)

    if new_metadata or new_snap is not None:
        for chunk_type, chunk_data in sf.raw_chunks:
            if chunk_type == 'tEXt' and new_metadata:
                null_pos = chunk_data.index(0)
                key = chunk_data[:null_pos].decode('latin-1')
                if key in new_metadata:
                    val = new_metadata[key].encode('latin-1')
                    new_chunk = chunk_data[:null_pos+1] + val
                else:
                    new_chunk = chunk_data
                _write_png_chunk(buf, 'tEXt', new_chunk)
            elif chunk_type == 'snAp' and new_snap is not None:
                _write_png_chunk(buf, 'snAp', new_snap)
            elif chunk_type != 'IEND':
                _write_png_chunk(buf, chunk_type, chunk_data)
        _write_png_chunk(buf, 'IEND', b'')
        return buf.getvalue()

    for chunk_type, chunk_data in sf.raw_chunks:
        _write_png_chunk(buf, chunk_type, chunk_data)

    return buf.getvalue()


def _write_png_chunk(buf: io.BytesIO, chunk_type: str, data: bytes):
    buf.write(struct.pack('>I', len(data)))
    buf.write(chunk_type.encode('latin-1'))
    buf.write(data)
    crc = zlib.crc32(chunk_type.encode('latin-1') + data) & 0xFFFFFFFF
    buf.write(struct.pack('>I', crc))
