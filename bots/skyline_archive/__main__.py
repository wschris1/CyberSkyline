"""Run with python -m bots.ws from the repository root."""

import argparse
import asyncio
import logging
import os

from .core import ArchiveError
from .settings import load_settings


class InstanceLock:
    """Release the process lock automatically even after a crash."""
    def __init__(self, directory):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.file = (directory / "bot.lock").open("a+b")

    def __enter__(self):
        try:
            if os.name == "nt":
                import msvcrt
                self.file.seek(0)
                self.file.write(b"0")
                self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise ArchiveError("Another bot process is using this state directory.") from exc
        return self

    def __exit__(self, *args):
        self.file.close()


def main():
    parser = argparse.ArgumentParser(description="Archive Cyber Skyline questions and watch for survey availability.")
    parser.add_argument("command", choices=("login", "run", "check"), help="Save login, run the Discord bot, or check configuration.")
    args = parser.parse_args()
    try:
        settings = load_settings(require_bot=args.command != "login", require_github=False)
        if args.command == "login":
            from .scanner import login
            with InstanceLock(settings.state_dir):
                asyncio.run(login(settings))
        elif args.command == "check":
            print("Discord configuration is valid. Credentials have not been tested against the services.")
            print("GitHub export:", "configured" if settings.github_token else "needs GITHUB_TOKEN; Discord-only scans can run")
            print("Saved Cyber Skyline login:", "present" if settings.auth_file.is_file() else "missing; run the login command")
        else:
            from .bot import WSBot
            logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
            with InstanceLock(settings.state_dir):
                WSBot(settings).run(settings.discord_token, log_handler=None)
    except ArchiveError as exc:
        parser.exit(1, str(exc) + "\n")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
