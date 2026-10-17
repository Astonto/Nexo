
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    executable = args.executable.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="nexo-package-check-") as directory:
        root = Path(directory)
        report_file = root / "startup.json"
        env = os.environ.copy()
        env.update(QT_QPA_PLATFORM="offscreen", NEXO_DATA_DIR=str(root / "data"))
        process = subprocess.Popen(
            [str(executable), "--smoke-test", "--smoke-report", str(report_file)],
            env=env, cwd=root, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            code = process.wait(timeout=60)
        except subprocess.TimeoutExpired:


            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            process.wait(timeout=10)
            raise RuntimeError("The executable did not finish the startup test within 60 seconds.")
        report = json.loads(report_file.read_text(encoding="utf-8")) if report_file.exists() else {}
        report["exit_code"] = code
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        expected = {"window_visible": True, "pages": 7, "icon_loaded": True,
                    "frozen": True, "resources": True, "global_hooks_disabled": True,
                    "privacy_provider_loaded": True, "input_driver_loaded": True,
                    "product_name": "Nexo", "version": "1.7.1", "accent": "#ff1744", "exit_code": 0,
                    "language": os.environ.get('NEXO_LANGUAGE', 'en'), "language_options": 2,
                    "translation_resources": True, "qt_translation": True,
                    "home": True, "sidebar_pages": 7, "home_message_interval": 7000, "home_message_count": 25,
                    "fixed_countdown_hidden": True, "recording_indicator_size": [460, 76], "recording_indicator_paused": True,
                    "visual_editor": True, "settings_tabs": 3,
                    "capture_strip": True, "readonly_shortcuts": True,
                    "keyboard_repeater": True, "recording_exclusions": 5,
                    "capture_flow": True, "capture_timing_editable_paused": True,
                    "capture_save_requires_stop": True, "window_target_selector": True, "stable_bottom": True,
                    "background_delivery": True, "flat_dark_palette": True,
                    "modifier_exclusions_available": True,
                    "playback_panel_size": [450, 75], "playback_pause_state": True,
                    "playback_progress": True}
        failed = [key for key, value in expected.items() if report.get(key) != value]
        if failed:
            raise RuntimeError(f"Package check failed: {', '.join(failed)}. {report}")
        print("Executable checked: startup and shutdown, seven sections, resources and Windows components.")
        print("Isolated test without global shortcuts or simulated input in other applications.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
