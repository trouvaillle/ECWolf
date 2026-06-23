import json
import base64
import io
import os
import webbrowser
from pathlib import Path

from aiohttp import web

from save_parser import parse_save, rebuild_save_file


class SaveAPI:
    def __init__(self, frontend_dir: str | None = None):
        self.save_file = None
        self.current_path = None
        self.frontend_dir = frontend_dir

    async def handle_open(self, request):
        data = await request.json()
        path = data.get('path', '')
        try:
            self.save_file = parse_save(path)
            self.current_path = path
            return await self._save_to_response()
        except Exception as e:
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
    app.router.add_get('/api/info', api.handle_get_info)
    app.router.add_post('/api/save', api.handle_save)
    app.router.add_get('/api/screenshot', api.handle_screenshot)
    app.router.add_get('/api/files', api.handle_list_files)

    if frontend_dir:
        app.router.add_get('/{path:.*}', api.handle_static)

    return app
