"""IPython magic commands for KITT."""

import logging

logger = logging.getLogger(__name__)


def load_ipython_extension(ipython):
    """Load KITT magic into IPython."""
    try:
        magics = KITTMagics(ipython)
        ipython.register_magics(magics)
        print("KITT magics loaded. Use %kitt to get started.")
    except Exception as e:
        print(f"Failed to load KITT magics: {e}")


class KITTMagics:
    """IPython magic commands for interacting with KITT.

    Usage:
        %kitt results --model Llama-3.1
        %kitt status
        %kitt compare model1 model2
        %%kitt run
        <campaign yaml here>
    """

    def __init__(self, shell=None) -> None:
        self.shell = shell
        self._store = None

    def _get_store(self):
        if self._store is None:
            try:
                from kitt.storage.sqlite_store import SQLiteStore

                self._store = SQLiteStore()
            except Exception:
                try:
                    from kitt.storage.json_store import JsonStore

                    self._store = JsonStore()
                except Exception:
                    pass
        return self._store

    def kitt(self, line: str) -> str | None:
        """Line magic: %kitt <command> [args]."""
        parts = line.strip().split()
        cmd = parts[0] if parts else "help"
        args = parts[1:]

        if cmd == "results":
            return self._results(args)
        elif cmd == "status":
            return self._status()
        elif cmd == "compare":
            return self._compare(args)
        elif cmd == "fingerprint":
            return self._fingerprint()
        elif cmd == "help":
            return self._help()
        else:
            return f"Unknown command: {cmd}. Use %kitt help for options."

    def kitt_cell(self, line: str, cell: str) -> str | None:
        """Cell magic: %%kitt run."""
        if line.strip() == "run":
            return self._run_campaign(cell)
        return "Usage: %%kitt run (then YAML in cell body)"

    def _results(self, args: list) -> str:
        store = self._get_store()
        if not store:
            return "No storage backend available."

        filters = {}
        i = 0
        while i < len(args):
            if args[i] == "--model" and i + 1 < len(args):
                filters["model"] = args[i + 1]
                i += 2
            elif args[i] == "--engine" and i + 1 < len(args):
                filters["engine"] = args[i + 1]
                i += 2
            else:
                i += 1

        results = store.query(filters=filters or None, order_by="-timestamp", limit=10)
        if not results:
            return "No results found."

        lines = [f"Found {len(results)} result(s):"]
        for r in results:
            status = "PASS" if r.get("passed") else "FAIL"
            lines.append(
                f"  {r.get('model', '?')} / {r.get('engine', '?')} "
                f"-- {status} ({r.get('timestamp', '?')[:19]})"
            )
        return "\n".join(lines)

    def _status(self) -> str:
        try:
            from kitt.campaign.state_manager import CampaignStateManager

            mgr = CampaignStateManager()
            campaigns = mgr.list_campaigns()
            if not campaigns:
                return "No campaigns found."
            latest = campaigns[-1]
            return (
                f"Latest: {latest['campaign_name']}\n"
                f"Status: {latest['status']}\n"
                f"Runs: {latest['total_runs']} | "
                f"Success: {latest['succeeded']} | "
                f"Failed: {latest['failed']}"
            )
        except Exception as e:
            return f"Error: {e}"

    def _compare(self, args: list) -> str:
        if len(args) < 2:
            return "Usage: %kitt compare <model> <engine>"
        store = self._get_store()
        if not store:
            return "No storage backend available."

        from kitt.bot.commands import BotCommandHandler

        handler = BotCommandHandler(result_store=store)
        return handler.handle_compare(args[0], args[1])

    def _fingerprint(self) -> str:
        from kitt.hardware.fingerprint import HardwareFingerprint

        return HardwareFingerprint.generate()

    def _run_campaign(self, yaml_text: str) -> str:
        try:
            import yaml

            config_data = yaml.safe_load(yaml_text)
            return f"Campaign config parsed: {config_data.get('campaign_name', 'unnamed')}\n(Dry run only in notebook mode)"
        except Exception as e:
            return f"Error parsing YAML: {e}"

    def _help(self) -> str:
        return (
            "KITT Jupyter Magic Commands:\n"
            "  %kitt results [--model X] [--engine Y]  Show recent results\n"
            "  %kitt status                             Show campaign status\n"
            "  %kitt compare <model> <engine>           Compare runs\n"
            "  %kitt fingerprint                        Show hardware fingerprint\n"
            "  %kitt help                               Show this help\n"
            "  %%kitt run                               Parse campaign YAML (cell magic)"
        )
