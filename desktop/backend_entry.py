"""Packaged local backend entry; no model loads at application startup."""
import multiprocessing
import os
from pathlib import Path
import sys


def main():
    multiprocessing.freeze_support()
    resources = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    os.environ.setdefault('AFS_RESOURCE_ROOT', str(resources))
    os.environ.setdefault('AFS_DESKTOP', '1')
    if not os.environ.get('AFS_API_TOKEN'):
        raise SystemExit('Desktop backend requires a per-launch API token')
    import uvicorn
    from apps.api.main import app
    configuration = uvicorn.Config(app, host='127.0.0.1', port=int(os.environ['AFS_PORT']),
                                  access_log=False, log_level='warning', loop='asyncio', http='h11')
    server = uvicorn.Server(configuration)
    app.state.request_shutdown = lambda: setattr(server, 'should_exit', True)
    server.run()


if __name__ == '__main__': main()
