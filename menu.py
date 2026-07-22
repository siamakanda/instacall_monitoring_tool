import sys
from config import load_settings, save_settings, setup_logging, validate_settings, get_credentials
from monitor import run_monitor
from quick import run_quick_check_balance, run_quick_check_summary, run_quick_check_full


def fmt_ids(ids):
    return ", ".join(ids) if ids else "none"


def fmt_pct(val):
    return f"{val:.0f}%" if val == int(val) else f"{val:.1f}%"


def hr(n=40):
    return "-" * n


def show_status(settings):
    ids = settings["customer_ids"]
    interval = settings["check_interval_seconds"]
    bal = settings["balance_threshold"]
    margin = settings["margin_threshold"]
    billed = settings["billed_min_threshold"]
    direction = settings.get("summary_direction", "outbound")
    sint = settings.get("summary_interval", "5m")

    print(f"  Monitored: {fmt_ids(ids)}")
    print(f"  Interval: {interval // 60} min  |  Balance alert below {bal:+.1f}")
    print(f"  Margin alert below {fmt_pct(margin)}  |  Billed min above {billed:.0f}")
    print(f"  Summary: {direction} / {sint}")
    audio = settings.get("audio_enabled", True)
    print(f"  Audio: {'ON' if audio else 'OFF'}")


def menu_settings(settings):
    fields = [
        ("customer_ids", "Customer IDs (comma-separated)", lambda v: [x.strip() for x in v.split(",") if x.strip()]),
        ("check_interval_seconds", "Check interval (seconds)", int),
        ("balance_threshold", "Balance alert threshold", float),
        ("margin_threshold", "Margin alert threshold (%)", float),
        ("billed_min_threshold", "Billed min threshold", float),
        ("request_timeout", "Request timeout (seconds)", int),
        ("summary_direction", "Summary direction (outbound/inbound)", str),
        ("summary_interval", "Summary interval (5m, 10m, 15m, 1h, etc.)", str),
        ("audio_enabled", "Audio alerts (true/false)", lambda v: v.lower() in ("true", "1", "yes", "on")),
        ("siren_loops", "Siren loops", int),
        ("siren_min_freq", "Siren min frequency (Hz)", int),
        ("siren_max_freq", "Siren max frequency (Hz)", int),
        ("siren_step_freq", "Siren step frequency (Hz)", int),
        ("siren_tone_duration", "Siren tone duration (ms)", int),
    ]

    while True:
        print()
        print("  Settings")
        print("  " + hr(40))
        for i, (key, label, _) in enumerate(fields, 1):
            val = settings[key]
            if isinstance(val, list):
                val = ", ".join(val)
            print(f"  {i:2}. {label}: {val}")
        print("   0. Back")
        print()

        choice = input("  Change #: ").strip()
        if choice == "0":
            break

        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(fields):
                print("  Invalid choice.")
                input("  Press Enter...")
                continue

            key, label, convert = fields[idx]
            current = settings[key]
            if isinstance(current, list):
                current = ", ".join(current)

            new_val = input(f"  {label} [{current}]: ").strip()
            if new_val == "":
                continue

            settings[key] = convert(new_val)
            save_settings(settings)
            print("  Saved.")
        except (ValueError, TypeError) as e:
            print(f"  Error: {e}")
        input("  Press Enter...")


def main():
    setup_logging()
    settings = load_settings()

    errors = validate_settings(settings)
    if errors:
        print("Invalid settings:")
        for e in errors:
            print(f"  - {e}")
        input("Press Enter to exit...")
        sys.exit(1)

    try:
        get_credentials()
    except ValueError as e:
        print(f"Credential error: {e}")
        input("Press Enter to exit...")
        sys.exit(1)

    while True:
        print()
        print("  Instacall Monitoring Tool")
        print("  " + hr(36))
        show_status(settings)
        print("  " + hr(36))
        print("  1. Start Monitor")
        print("  2. Quick Check - Balances")
        print("  3. Quick Check - Summary")
        print("  4. Quick Check - Full")
        print("  5. Settings")
        print("  6. Exit")
        print()

        choice = input("  > ").strip()

        if choice == "1":
            run_monitor(settings)
        elif choice == "2":
            run_quick_check_balance(settings)
        elif choice == "3":
            run_quick_check_summary(settings)
        elif choice == "4":
            run_quick_check_full(settings)
        elif choice == "5":
            menu_settings(settings)
            settings = load_settings()
        elif choice == "6":
            print("  Exit.")
            sys.exit(0)
        else:
            print("  Invalid choice.")


if __name__ == "__main__":
    main()
