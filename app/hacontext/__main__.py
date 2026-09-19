"""Entry point for the terminal, direct export and internal worker."""
from __future__ import annotations
import argparse
import fcntl
import os
from pathlib import Path
import sys
from . import __version__
from .state import Store,safe_error


def main(argv=None):
    parser=argparse.ArgumentParser(description='Home Assistant context. Run without arguments for the full interface.')
    parser.add_argument('command',nargs='?',choices=['export'],help='optional noninteractive export using saved settings')
    parser.add_argument('--version',action='version',version='ha-context '+__version__)
    parser.add_argument('--worker',metavar='ROOT',help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    if args.worker:
        from .processes import prepare_worker
        prepare_worker()
        from .worker import main as worker_main
        return worker_main(args.worker)
    root=Path(__file__).resolve().parents[2]
    store=Store(root)
    try:
        store.initialize()
        lock_path=store.local/'session.lock'
        if lock_path.is_symlink():raise ValueError('Unsafe lock path.')
        lock=os.open(lock_path,os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(lock);raise ValueError('ha-context is already open. Close the other session before opening another.')
        try:
            if args.command=='export':
                if store.load() is None:raise ValueError('Open ha-context and complete onboarding first.')
                from .worker import run_export
                output,summary=run_export(store,print)
                print(summary['status']+' — '+str(output/'ha-context.txt'))
                return 0 if summary['status']=='Complete' else 2
            if not sys.stdin.isatty():raise ValueError('A terminal is required for the menu. Open an interactive SSH session.')
            from .ui import ContextUI
            ui=ContextUI(store);ui.run()
            if ui.uninstall_requested:print('ha-context was removed. Home Assistant was not changed.')
            return 0
        finally:os.close(lock)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print('ha-context: '+safe_error(exc),file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
