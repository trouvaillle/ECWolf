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


# ─── FArchive Reader ─────────────────────────────────────────────────────

class FArchiveReader:
    """Reads ECWolf's big-endian FArchive binary format."""

    def __init__(self, data: bytes, save_version: int, save_prod_version: int):
        self.data = data
        self.pos = 0
        self.save_version = save_version
        self.save_prod_version = save_prod_version
        self.name_table: list[str] = []
        self.class_table: list[str] = []

    def remaining(self) -> int:
        return len(self.data) - self.pos

    def _ensure(self, n: int):
        if self.pos + n > len(self.data):
            raise EOFError(f"Unexpected end of FArchive at offset 0x{self.pos:04x}")

    # ── Primitive types (big-endian) ──

    def u8(self) -> int:
        self._ensure(1)
        v = self.data[self.pos]
        self.pos += 1
        return v

    def u16(self) -> int:
        self._ensure(2)
        v = struct.unpack('>H', self.data[self.pos:self.pos+2])[0]
        self.pos += 2
        return v

    def i16(self) -> int:
        self._ensure(2)
        v = struct.unpack('>h', self.data[self.pos:self.pos+2])[0]
        self.pos += 2
        return v

    def u32(self) -> int:
        self._ensure(4)
        v = struct.unpack('>I', self.data[self.pos:self.pos+4])[0]
        self.pos += 4
        return v

    def i32(self) -> int:
        self._ensure(4)
        v = struct.unpack('>i', self.data[self.pos:self.pos+4])[0]
        self.pos += 4
        return v

    def f32(self) -> float:
        self._ensure(4)
        v = struct.unpack('>f', self.data[self.pos:self.pos+4])[0]
        self.pos += 4
        return v

    def bool8(self) -> bool:
        return self.u8() != 0

    # ── Variable-length integer (LEB128-like, little-endian) ──

    def varint(self) -> int:
        count = 0
        shift = 0
        while True:
            b = self.u8()
            count |= (b & 0x7F) << shift
            shift += 7
            if not (b & 0x80):
                break
        return count

    # ── FString (ReadCount length + bytes, no null terminator stored) ──

    def read_string(self) -> str:
        length = self.varint()
        if length == 0:
            return ''
        self._ensure(length - 1)
        s = self.data[self.pos:self.pos + length - 1].decode('latin-1')
        self.pos += length - 1
        return s

    # ── FName (0x21=NULL, 0x1B=NEW_NAME, 0x1C=OLD_NAME) ──

    def read_name(self) -> Optional[str]:
        tag = self.u8()
        if tag == 0x21:  # NIL_NAME
            return None
        elif tag == 0x1B:  # NEW_NAME
            length = self.varint()
            if length == 0:
                s = ''
            else:
                self._ensure(length - 1)
                s = self.data[self.pos:self.pos + length - 1].decode('latin-1')
                self.pos += length - 1
            self.name_table.append(s)
            return s
        elif tag == 0x1C:  # OLD_NAME
            idx = self.varint()
            return self.name_table[idx] if idx < len(self.name_table) else None
        else:
            raise ValueError(f"Unknown FName tag: 0x{tag:02x} at offset 0x{self.pos-1:04x}")

    # ── ClassDef* (UserWriteClass / UserReadClass) ──

    def read_class_def(self) -> Optional[str]:
        """Returns class name or None."""
        tag = self.u8()
        if tag == 0x02:  # NULL
            return None
        elif tag == 0x01:  # NEW_CLASS
            name = self.read_string()
            self.class_table.append(name)
            return name
        elif tag == 0x00:  # OLD_CLASS (existing)
            idx = self.varint()
            return self.class_table[idx] if idx < len(self.class_table) else None
        else:
            raise ValueError(f"Unknown ClassDef tag: 0x{tag:02x} at offset 0x{self.pos-1:04x}")

    # ── Frame* (ClassDef* + DWORD frame index) ──

    def read_frame_ptr(self) -> Optional[dict]:
        cls = self.read_class_def()
        if cls is None:
            return None
        frame_idx = self.u32()
        return {'class': cls, 'frameIndex': frame_idx}

    # ── FTextureID (FName + WriteCount useType) ──

    def read_texture_id(self) -> Optional[dict]:
        name = self.read_name()
        if name is None:
            return None
        use_type = self.varint()
        return {'name': name, 'useType': use_type}

    # ── Sprite (0x0B=NEW_SPRITE, 0x0C=OLD_SPRITE) ──

    def read_sprite(self) -> int:
        tag = self.u8()
        if tag == 0x0B:  # NEW_SPRITE
            self._ensure(4)
            self.pos += 4  # sprite name (4 bytes)
            hint = self.varint()
            return hint
        elif tag == 0x0C:  # OLD_SPRITE
            return self.varint()
        else:
            raise ValueError(f"Unknown sprite tag: 0x{tag:02x} at offset 0x{self.pos-1:04x}")

    # ── Object reference (TObjPtr serialization) ──
    # Returns a dict describing what was read without full object parse.

    OBJ_NULL = 0x04
    OBJ_M1 = 0x2C
    OBJ_OLD = 0x03
    OBJ_NEW = 0x01
    OBJ_NEW_CLS = 0x02
    OBJ_NEW_PLYR = 0x05
    OBJ_NEW_PLYR_CLS = 0x06

    def read_obj_ref(self) -> dict:
        """Read an object reference and return info about it.
        If it's a NEW object, skip its serialization data.
        Set parse_obj=True to actually store the skipped range for later editing.
        """
        tag = self.u8()
        if tag == self.OBJ_NULL:
            return {'tag': 'null'}
        elif tag == self.OBJ_M1:
            return {'tag': 'm1'}
        elif tag == self.OBJ_OLD:
            idx = self.varint()
            return {'tag': 'old', 'index': idx}
        elif tag == self.OBJ_NEW_PLYR_CLS:
            player_num = self.u8()
            # fall through to NEW_CLS_OBJ logic
            cls_name = self.read_string()
            self.class_table.append(cls_name)
            start = self.pos
            self._skip_object(cls_name)
            return {'tag': 'new_plyr_cls', 'playerNum': player_num, 'class': cls_name,
                    'dataRange': (start, self.pos)}
        elif tag == self.OBJ_NEW_CLS:
            cls_name = self.read_string()
            self.class_table.append(cls_name)
            start = self.pos
            self._skip_object(cls_name)
            return {'tag': 'new_cls', 'class': cls_name,
                    'dataRange': (start, self.pos)}
        elif tag == self.OBJ_NEW_PLYR:
            player_num = self.u8()
            cls_idx = self.varint()
            cls_name = self.class_table[cls_idx] if cls_idx < len(self.class_table) else f'class#{cls_idx}'
            start = self.pos
            self._skip_object(cls_name)
            return {'tag': 'new_plyr', 'playerNum': player_num, 'class': cls_name,
                    'dataRange': (start, self.pos)}
        elif tag == self.OBJ_NEW:
            cls_idx = self.varint()
            cls_name = self.class_table[cls_idx] if cls_idx < len(self.class_table) else f'class#{cls_idx}'
            start = self.pos
            self._skip_object(cls_name)
            return {'tag': 'new', 'class': cls_name,
                    'dataRange': (start, self.pos)}
        else:
            raise ValueError(f"Unknown object tag: 0x{tag:02x} at offset 0x{self.pos-1:04x}")

    def _skip_object(self, cls_name: str):
        """Skip through an object's serialization data.
        We read all fields but discard them."""
        if cls_name in ('AWeapon', 'Weapon'):
            self._skip_aweapon()
        elif cls_name in ('AInventory', 'Inventory', 'Ammo', 'AAmmo', 'Key', 'AKey',
                          'Clip', 'Food', 'Medikit', 'Well', 'Blood', 'Chalice',
                          'Crown', 'MachineGun', 'Pistol', 'Knife',
                          'GreenBarrel', 'Barrel', 'Gibs', 'Bones1', 'Bones3',
                          'HangedMan', 'WhitePillar', 'CeilingLight', 'Puddle',
                          'EmptyWell', 'Vines', 'ChestofJewels', 'SkeletonFlat',
                          'GatlingGunUpgrade'):
            self._skip_ainventory()
        elif cls_name in ('APlayerPawn', 'PlayerPawn', 'BJPlayer', 'Wolf2Map1', 'Wolf2'):
            self._skip_aplayerpawn()
        elif cls_name == 'Actor':
            self._skip_actor()
        elif cls_name == 'Thinker':
            self._skip_thinker()
        elif cls_name == 'DObject':
            self._skip_dobject()
        else:
            # Unknown class - try as actor-based (most game objects inherit AActor)
            self._skip_actor()

    def _skip_dobject(self):
        pass  # DObject::Serialize does nothing

    def _skip_thinker(self):
        if self.save_version > 1451884199:
            self.u8()  # priority
        self._skip_dobject()

    def _skip_actor(self):
        self.read_sprite()           # sprite
        self.u8()                     # dir
        self.u32()                    # flags
        self.i32()                    # distance
        self.i32()                    # x
        self.i32()                    # y
        if self.save_prod_version >= 0x001003FF and self.save_version >= 1507591295:
            self.i32()                # z
        self.i32()                    # velx
        self.i32()                    # vely
        self.u32()                    # angle
        self.u32()                    # pitch
        self.i32()                    # health
        self.i32()                    # speed
        self.i32()                    # runspeed
        self.i32()                    # points
        self.i32()                    # radius
        self.i32()                    # ticcount
        self.read_frame_ptr()         # state
        self.i32()                    # viewx
        self.i32()                    # viewheight
        self.i32()                    # transx
        self.i32()                    # transy
        if self.save_version >= 1393719642:
            self.read_texture_id()    # overheadIcon
        self.i32()                    # sighttime
        self.i32()                    # sightrandom
        self.i32()                    # minmissilechance
        self.i32()                    # painchance
        self.i32()                    # missilefrequency
        self.i32()                    # movecount
        self.i32()                    # meleerange
        self.read_name()              # activesound
        self.read_name()              # attacksound
        self.read_name()              # deathsound
        self.read_name()              # seesound
        self.read_name()              # painsound
        self.i32()                    # temp1
        self.u8()                     # hidden (BYTE)
        self.varint()                 # player (SerializePointer - WriteCount)
        self.read_obj_ref()           # inventory
        self.i32()                    # soundZone
        if self.save_prod_version >= 0x001003FF and self.save_version >= 1459043051:
            self.read_obj_ref()       # target
        if self.save_version < 1382102747 or self.save_prod_version < 0x001002FF:
            self.read_obj_ref()       # proxy (old compat)
        self.u8()                     # hasActorRef (bool)
        if self.save_prod_version >= 0x001002FF and self.save_version > 1374914454:
            self.i32()                # projectilepassheight
        self._skip_thinker()

    def _skip_aplayerpawn(self):
        self.i32()   # maxhealth
        self._skip_actor()

    def _skip_ainventory(self):
        self.u32()                    # itemFlags
        self.read_obj_ref()           # owner
        self.read_name()              # pickupsound
        self.u32()                    # amount
        self.u32()                    # maxamount
        self.u32()                    # interhubamount
        self.read_texture_id()        # icon
        if self.save_version > 1672116695:
            self.u32()                # respawnTimer
        self._skip_actor()

    def _skip_aweapon(self):
        self.u8()                     # mode
        self.read_class_def()         # ammotype[0]
        self.i32()                    # ammogive[0]
        self.u32()                    # ammouse[0]
        self.i32()                    # yadjust
        self.read_obj_ref()           # ammo[0]
        if self.save_prod_version >= 0x001002FF and self.save_version > 1374729160:
            self.read_class_def()     # ammotype[1]
            self.i32()                # ammogive[1]
            self.u32()                # ammouse[1]
            self.read_obj_ref()       # ammo[1]
            self.f32()                # fovscale
        self._skip_ainventory()

    # ── High-level skip helpers ──

    def skip_thinker_list(self):
        """Skip the entire thinker list (5 priorities, each null-terminated)."""
        for _ in range(5):  # NUM_TYPES = 5
            while True:
                ref = self.read_obj_ref()
                if ref['tag'] == 'null':
                    break


# ─── Parse structured game state from snAp ──────────────────────────────

@dataclass
class GameState:
    difficulty: int = 0
    player_class: str = ''
    secretcount: int = 0
    treasurecount: int = 0
    killcount: int = 0
    secrettotal: int = 0
    treasuretotal: int = 0
    killtotal: int = 0
    time_count: int = 0
    victory_flag: bool = False
    fullmap: bool = False
    kill_ratio: int = 0
    secrets_ratio: int = 0
    treasure_ratio: int = 0
    num_levels: int = 0
    level_time: int = 0
    level_par: int = 0
    # player_t fields
    player_state: int = 0
    player_health: int = 0
    player_score: int = 0
    player_lives: int = 0
    player_fov: float = 90.0
    player_frags: int = 0
    player_respawn: int = -1

    raw_top_level_end: int = 0  # offset after top-level, before thinker list
    raw_player_end: int = 0     # offset after player_t
    raw_data: bytes = b''       # original data for range-based editing
    field_offsets: dict = field(default_factory=dict)  # field_name -> (offset, size_bytes, type)


def _track(gs: GameState, offsets: dict, name: str, size: int, ty: str):
    offsets[name] = (gs._ar_pos_before, size, ty)


def parse_snap_gamestate(snap_data: bytes, save_version: int, save_prod_version: int) -> GameState:
    """Parse structured game state from decompressed snAp data."""
    gs = GameState()
    gs.raw_data = snap_data
    ar = FArchiveReader(snap_data, save_version, save_prod_version)

    offsets = {}

    def track(name, size, ty):
        offsets[name] = (ar.pos, size, ty)

    # ── Top-level Serialize ──
    track('difficulty', 2, 'i16')
    gs.difficulty = ar.i16()

    pc_start = ar.pos
    gs.player_class = ar.read_class_def() or ''
    offsets['player_class'] = (pc_start, ar.pos - pc_start, 'raw')

    if save_version >= 1599444347:
        track('max_players', 4, 'u32')
        max_players = ar.u32()
        for _ in range(1, max_players):
            ar.read_class_def()

    track('secretcount', 4, 'i32')
    gs.secretcount = ar.i32()
    track('treasurecount', 4, 'i32')
    gs.treasurecount = ar.i32()
    track('killcount', 4, 'i32')
    gs.killcount = ar.i32()
    track('secrettotal', 4, 'i32')
    gs.secrettotal = ar.i32()
    track('treasuretotal', 4, 'i32')
    gs.treasuretotal = ar.i32()
    track('killtotal', 4, 'i32')
    gs.killtotal = ar.i32()
    track('time_count', 4, 'i32')
    gs.time_count = ar.i32()
    track('victory_flag', 1, 'u8')
    gs.victory_flag = ar.bool8()

    if save_version >= 1393719642:
        track('fullmap', 1, 'u8')
        gs.fullmap = ar.bool8()

    track('kill_ratio', 4, 'u32')
    gs.kill_ratio = ar.u32()
    track('secrets_ratio', 4, 'u32')
    gs.secrets_ratio = ar.u32()
    track('treasure_ratio', 4, 'u32')
    gs.treasure_ratio = ar.u32()
    track('num_levels', 4, 'u32')
    gs.num_levels = ar.u32()
    track('level_time', 4, 'i32')
    gs.level_time = ar.i32()

    if save_version > 1395865826:
        track('level_par', 4, 'i32')
        gs.level_par = ar.i32()

    gs.raw_top_level_end = ar.pos

    # ── Skip thinker list (may fail for complex data) ──
    try:
        ar.skip_thinker_list()

        # ── map FString (SerializePointer) ──
        ar.varint()  # map index (or ~0u for NULL)

        # ── player_t::Serialize ──
        track('player_state', 1, 'u8')
        gs.player_state = ar.u8()

        ar.read_obj_ref()   # mo
        ar.read_obj_ref()   # camera
        ar.read_obj_ref()   # killerobj

        ar.i32()                        # oldscore
        track('player_score', 4, 'i32')
        gs.player_score = ar.i32()
        ar.i32()                        # nextextra
        track('player_lives', 2, 'i16')
        gs.player_lives = ar.i16()
        track('player_health', 4, 'i32')
        gs.player_health = ar.i32()

        ar.read_obj_ref()   # ReadyWeapon
        ar.read_obj_ref()   # PendingWeapon

        ar.u32()            # flags
        ar.i16()            # extralight

        # psprite[0]
        ar.read_frame_ptr()
        ar.i16()            # ticcount
        ar.i32()            # sx
        ar.i32()            # sy

        # psprite[1]
        ar.read_frame_ptr()
        ar.i16()            # ticcount
        ar.i32()            # sx
        ar.i32()            # sy

        if save_prod_version >= 0x001002FF and save_version > 1374729160:
            track('player_fov', 4, 'f32')
            gs.player_fov = ar.f32()
            ar.f32()  # DesiredFOV

        if save_version > 1672116695:
            track('player_frags', 4, 'i32')
            gs.player_frags = ar.i32()

        if save_version > 1690159133:
            track('player_respawn', 4, 'i32')
            gs.player_respawn = ar.i32()

        gs.raw_player_end = ar.pos
    except Exception:
        pass  # player fields not available

    gs.field_offsets = offsets
    return gs


def _encode_value(value, ty: str) -> bytes:
    import struct
    if ty == 'i16':
        return struct.pack('>h', int(value))
    elif ty == 'u16':
        return struct.pack('>H', int(value))
    elif ty == 'i32':
        return struct.pack('>i', int(value))
    elif ty == 'u32':
        return struct.pack('>I', int(value))
    elif ty == 'f32':
        return struct.pack('>f', float(value))
    elif ty == 'u8':
        return bytes([int(value) & 0xFF])
    elif ty == 'raw':
        return value.encode('latin-1') if isinstance(value, str) else bytes(value)
    else:
        raise ValueError(f"Unknown type: {ty}")


def apply_gamestate_patches(data: bytes, save_version: int, save_prod_version: int, changes: dict) -> bytes:
    """Apply structured field changes to raw snAp data.
    
    `changes` is a dict of field_name -> new_value.
    Field names must match those recorded by parse_snap_gamestate field_offsets.
    
    Returns the patched data bytes.
    """
    # Re-parse to get current field offsets
    gs = parse_snap_gamestate(data, save_version, save_prod_version)
    result = bytearray(data)

    for field_name, new_value in changes.items():
        if field_name not in gs.field_offsets:
            continue
        offset, size, ty = gs.field_offsets[field_name]
        encoded = _encode_value(new_value, ty)
        if len(encoded) != size:
            # If size mismatch (e.g., variable-length raw), skip
            continue
        result[offset:offset + size] = encoded

    return bytes(result)
