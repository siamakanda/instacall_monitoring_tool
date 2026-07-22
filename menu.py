import sys
from balance_alert import (
    load_settings,
    save_settings,
    run_monitor,
    run_quick_check_balance,
    run_quick_check_summary,
    run_quick_check_full,
    DEFAULT_SETTINGS,
)


def print_header():
    print()
    print("=" * 50)
    print("  Instacall Balance & Margin Monitor")
    print("=" * 50)


def show_status(settings):
    ids = settings["customer_ids"]
    interval = settings["check_interval_seconds"]
    bal = settings["balance_threshold"]
    margin = settings["margin_threshold"]
    billed = settings["billed_min_threshold"]
    direction = settings.get("summary_direction", "outbound")
    sint = settings.get("summary_interval", "5m")
    print(f"  IDs: {ids}")
    print(f"  Interval: {interval // 60} min   |   Balance Alert: < {bal}")
    print(f"  Margin Alert: < {margin}%   |   Billed Min > {billed}")
    print(f"  Summary: {direction} / {sint}")
    print("-" * 50)


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
        ("siren_loops", "Siren loops", int),
        ("siren_min_freq", "Siren min frequency (Hz)", int),
        ("siren_max_freq", "Siren max frequency (Hz)", int),
        ("siren_step_freq", "Siren step frequency (Hz)", int),
        ("siren_tone_duration", "Siren tone duration (ms)", int),
    ]

    while True:
        print_header()
        print("  Settings")
        print("-" * 50)
        for i, (key, label, _) in enumerate(fields, 1):
            val = settings[key]
            if isinstance(val, list):
                val = ", ".join(val)
            print(f"  {i:2}. {label}: {val}")
        print("   0. Back to main menu")
        print()

        choice = input("  Change setting #: ").strip()
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

            new_val = input(f"  New value for '{label}' [{current}]: ").strip()
            if new_val == "":
                continue

            settings[key] = convert(new_val)
            save_settings(settings)
            print(f"  Saved.")
        except (ValueError, TypeError) as e:
            print(f"  Error: {e}")
        input("  Press Enter...")


def main():
    settings = load_settings()

    while True:
        print_header()
        show_status(settings)
        print("  1. Start Continuous Monitor")
        print("  2. Quick Check - Balance")
        print("  3. Quick Check - Summary Report")
        print("  4. Quick Check - Full (Balance + Summary)")
        print("  5. Settings")
        print("  6. Exit")
        print()

        choice = input("  Choice: ").strip()

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
            print("  Goodbye.")
            sys.exit(0)
        else:
            print("  Invalid choice. Press Enter...")
            input()


if __name__ == "__main__":
    main()
