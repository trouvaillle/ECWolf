import asyncio
import json
import base64
import concurrent.futures
import io
import os
import webbrowser
from pathlib import Path

from aiohttp import web

from save_parser import parse_save, rebuild_save_file, _compress_snap


class SaveAPI:
    def __init__(self, frontend_dir: str | None = None):
        self.save_file = None
        self.current_path = None
        self.frontend_dir = frontend_dir

    async def handle_open(self, request):
        data = await request.json()
        path = data.get('path', '')
        print(f"[api] open requested: path={path!r}")
        try:
            self.save_file = parse_save(path)
            self.current_path = path
            print(f"[api] open success: version={self.save_file.save_version}")
            return await self._save_to_response()
        except Exception as e:
            print(f"[api] open failed: {e}")
            return web.json_response({'error': str(e)}, status=400)

    async def handle_browse(self, request):
        """Open native file dialog (runs tkinter in a thread)."""
        try:
            import tkinter as tk
            from tkinter import filedialog
        except ImportError:
            return web.json_response({'error': 'tkinter not available'}, status=501)

        def _dialog():
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            root.lift()
            path = filedialog.askopenfilename(
                title="Select ECWolf Save File",
                filetypes=[("ECWolf Save Files", "*.ecs"), ("All Files", "*.*")],
            )
            root.destroy()
            return path

        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            path = await loop.run_in_executor(pool, _dialog)

        if not path:
            return web.json_response({'cancelled': True})

        try:
            self.save_file = parse_save(path)
            self.current_path = path
            return await self._save_to_response()
        except Exception as e:
            print(f"[api] browse open failed: {e}")
            return web.json_response({'error': str(e)}, status=400)

    async def handle_get_info(self, request):
        if not self.save_file:
            return web.json_response({'error': 'No save file loaded'}, status=400)
        return await self._save_to_response()

    async def handle_save(self, request):
        if not self.save_file:
            return web.json_response({'error': 'No save file loaded'}, status=400)

        data = await request.json()
        new_meta = data.get('metadata', None)
        save_path = data.get('path', self.current_path)

        if new_meta:
            new_data = rebuild_save_file(self.save_file, new_meta)
            with open(save_path, 'wb') as f:
                f.write(new_data)
            self.save_file = parse_save(save_path)
            self.current_path = save_path

        return await self._save_to_response()

    async def handle_screenshot(self, request):
        if not self.save_file or not self.save_file.screenshot:
            return web.json_response({'error': 'No screenshot'}, status=400)

        buf = io.BytesIO()
        self.save_file.screenshot.save(buf, 'PNG')
        b64 = base64.b64encode(buf.getvalue()).decode('ascii')
        return web.json_response({'image': f'data:image/png;base64,{b64}'})

    async def handle_snap(self, request):
        if not self.save_file:
            return web.json_response({'error': 'No save file loaded'}, status=400)
        d = self.save_file.snap_decompressed
        if d is None:
            return web.json_response({'error': 'No snAp data'}, status=400)
        return web.json_response({
            'hex': d.hex(),
            'size': len(d),
        })

    async def handle_snap_patch(self, request):
        if not self.save_file:
            return web.json_response({'error': 'No save file loaded'}, status=400)

        data = await request.json()
        new_meta = data.get('metadata', None)
        offset = data.get('offset')
        hex_data = data.get('hex')
        save_path = data.get('path', self.current_path)

        if offset is not None and hex_data is not None:
            d = bytearray(self.save_file.snap_decompressed)
            patch = bytes.fromhex(hex_data)
            if offset < 0 or offset + len(patch) > len(d):
                return web.json_response({'error': 'Patch out of bounds'}, status=400)
            d[offset:offset+len(patch)] = patch
            new_snap = _compress_snap(d, self.save_file.snap_compressed)
            new_data = rebuild_save_file(self.save_file, new_meta, new_snap)
        elif new_meta:
            new_data = rebuild_save_file(self.save_file, new_meta)
        else:
            return web.json_response({'error': 'Nothing to patch'}, status=400)

        with open(save_path, 'wb') as f:
            f.write(new_data)
        self.save_file = parse_save(save_path)
        self.current_path = save_path
        return await self._save_to_response()

    async def handle_list_files(self, request):
        path = request.query.get('dir', '')
        if not path:
            path = os.path.expanduser('~')
        files = []
        try:
            for entry in os.scandir(path):
                if entry.is_file() and entry.name.lower().endswith('.ecs'):
                    files.append({
                        'name': entry.name,
                        'path': entry.path,
                        'size': entry.stat().st_size,
                        'modified': entry.stat().st_mtime,
                    })
                elif entry.is_dir() and not entry.name.startswith('.'):
                    files.append({
                        'name': entry.name + '/',
                        'path': entry.path,
                        'dir': True,
                    })
        except PermissionError:
            pass
        return web.json_response({'files': files, 'current': path})

    async def _save_to_response(self):
        sf = self.save_file
        meta = dict(sf.metadata) if sf.metadata else {}
        info = {
            'path': sf.path,
            'metadata': meta,
            'saveVersion': sf.save_version,
            'saveProdVersion': sf.save_prod_version,
            'snapSize': len(sf.snap_compressed) if sf.snap_compressed else 0,
            'snapDecompressedSize': len(sf.snap_decompressed) if sf.snap_decompressed else 0,
            'hasScreenshot': sf.screenshot is not None,
        }
        return web.json_response(info)

    async def handle_static(self, request):
        if not self.frontend_dir:
            return web.Response(text='Frontend not available', status=404)

        path = request.match_info.get('path', '')
        if not path or path == '/' or path.endswith('/'):
            path = 'index.html'

        filepath = Path(self.frontend_dir) / path
        if not filepath.exists() or not filepath.is_file():
            filepath = Path(self.frontend_dir) / 'index.html'

        content = filepath.read_bytes()
        ext = filepath.suffix.lower()
        mime_types = {
            '.html': 'text/html',
            '.js': 'application/javascript',
            '.css': 'text/css',
            '.png': 'image/png',
            '.svg': 'image/svg+xml',
            '.ico': 'image/x-icon',
            '.json': 'application/json',
            '.woff2': 'font/woff2',
        }
        ct = mime_types.get(ext, 'application/octet-stream')
        return web.Response(body=content, content_type=ct)


def create_app(frontend_dir: str | None = None) -> web.Application:
    api = SaveAPI(frontend_dir=frontend_dir)
    app = web.Application()

    app.router.add_post('/api/open', api.handle_open)
    app.router.add_post('/api/browse', api.handle_browse)
    app.router.add_get('/api/info', api.handle_get_info)
    app.router.add_post('/api/save', api.handle_save)
    app.router.add_get('/api/screenshot', api.handle_screenshot)
    app.router.add_get('/api/snap', api.handle_snap)
    app.router.add_post('/api/snap_patch', api.handle_snap_patch)
    app.router.add_get('/api/files', api.handle_list_files)

    if frontend_dir:
        app.router.add_get('/{path:.*}', api.handle_static)

    return app
