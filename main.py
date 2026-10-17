if __name__ == "__main__":
    import sys
    try:
        from macroflow.app import main
        raise SystemExit(main())
    except Exception as exc:


        if "--smoke-test" in sys.argv and "--smoke-report" in sys.argv:
            import json
            import traceback
            from pathlib import Path
            report = Path(sys.argv[sys.argv.index("--smoke-report") + 1])
            report.write_text(json.dumps({"startup_error": type(exc).__name__, "detail": str(exc),
                                          "traceback": traceback.format_exc()}, indent=2), encoding="utf-8")
            raise SystemExit(2)
        raise
