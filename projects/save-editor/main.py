import asyncio
import threading
import webbrowser
from pathlib import Path

from aiohttp import web
from api_server import create_app


HOST = '127.0.0.1'
PORT = 8765


def find_frontend_dir() -> str | None:
    candidates = [
        Path(__file__).parent / 'frontend' / 'dist',
        Path(__file__).parent / 'dist',
    ]
    for c in candidates:
        if (c / 'index.html').exists():
            return str(c.resolve())
    return None


def start_server(frontend_dir: str | None) -> str:
    app = create_app(frontend_dir=frontend_dir)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    runner = web.AppRunner(app)
    loop.run_until_complete(runner.setup())
    site = web.TCPSite(runner, HOST, PORT)
    loop.run_until_complete(site.start())
    url = f'http://{HOST}:{PORT}/'

    def run_loop():
        loop.run_forever()

    t = threading.Thread(target=run_loop, daemon=True)
    t.start()
    return url


def main():
    frontend_dir = find_frontend_dir()
    if frontend_dir:
        print(f'Serving frontend from: {frontend_dir}')

    url = start_server(frontend_dir)
    print(f'Save Editor running at: {url}')

    if not frontend_dir:
        print('No frontend build found. Run the frontend dev server:')
        print('  cd frontend && npm run dev')
        print(f'Then open your browser to: {url}')

    try:
        import webview
        webview.create_window('ECWolf Save Editor', url, width=1024, height=768)
        webview.start()
    except ImportError:
        webbrowser.open(url)
        print('Press Ctrl+C to stop...')
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
