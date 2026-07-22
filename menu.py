from __future__ import annotations

import sys
from typing import Any, Callable, Optional

from config import (
    Settings,
    get_credentials,
    load_profiles,
    load_settings,
    save_profiles,
    save_settings,
    setup_logging,
    validate_settings,
)
from export import export_balance_csv, export_margin_csv
from monitor import run_monitor
from persistence import get_balance_history, get_margin_history, init_db
from quick import run_quick_check_balance, run_quick_check_full, run_quick_check_summary, run_quick_check_parallel


def fmt_ids(ids: list[str]) -> str:
    return ", ".join(ids) if ids else "none"


def fmt_pct(val: float) -> str:
    return f"{val:.0f}%" if val == int(val) else f"{val:.1f}%"


def hr(n: int = 40) -> str:
    return "-" * n


def show_status(settings: Settings) -> None:
    ids = settings.customer_ids
    interval = settings.check_interval_seconds
    bal = settings.balance_threshold
    margin = settings.margin_threshold
    billed = settings.billed_min_threshold
    direction = settings.summary_direction
    sint = settings.summary_interval

    print(f"  Profile: {settings.active_profile}")
    print(f"  Monitored: {fmt_ids(ids)}")
    if interval >= 60 and interval % 60 == 0:
        print(f"  Interval: {interval // 60} min  |  Balance alert below {bal:+.1f}")
    elif interval >= 60:
        print(f"  Interval: {interval // 60}m {interval % 60}s  |  Balance alert below {bal:+.1f}")
    else:
        print(f"  Interval: {interval}s  |  Balance alert below {bal:+.1f}")
    print(f"  Margin alert below {fmt_pct(margin)}  |  Billed min above {billed:.0f}")
    print(f"  Summary: {direction} / {sint}")
    print(f"  Cooldown: {settings.alert_cooldown_seconds}s")
    audio = settings.audio_enabled
    print(f"  Audio: {'ON' if audio else 'OFF'}  |  Webhooks: {settings.webhook_type}")


def menu_settings(settings: Settings) -> Settings:
    field_config: list[tuple[str, str, Callable[[str], object]]] = [
        ("customer_ids", "Customer IDs (comma-separated)", lambda v: [x.strip() for x in v.split(",") if x.strip()]),
        ("check_interval_seconds", "Check interval (seconds)", int),
        ("balance_threshold", "Balance alert threshold", float),
        ("margin_threshold", "Margin alert threshold (%)", float),
        ("billed_min_threshold", "Billed min threshold", float),
        ("db_retention_days", "DB retention (days, 0=keep all)", int),
        ("active_hours_start", "Active hours start (HH:MM, empty=24/7)", str),
        ("active_hours_end", "Active hours end (HH:MM, empty=24/7)", str),
        ("active_days", "Active days (mon,tue,wed,thu,fri,sat,sun, empty=all)", str),
        ("logging_json", "JSON logging (true/false)", lambda v: v.lower() in ("true", "1", "yes", "on")),
        ("health_port", "Health HTTP port (0=disabled)", int),
        ("request_timeout", "Request timeout (seconds)", int),
        ("summary_direction", "Summary direction (outbound/inbound)", str),
        ("summary_interval", "Summary interval (5m, 10m, 15m, 1h, etc.)", str),
        ("audio_enabled", "Audio alerts (true/false)", lambda v: v.lower() in ("true", "1", "yes", "on")),
        ("alert_cooldown_seconds", "Alert cooldown (seconds)", int),
        ("siren_loops", "Siren loops", int),
        ("siren_min_freq", "Siren min frequency (Hz)", int),
        ("siren_max_freq", "Siren max frequency (Hz)", int),
        ("siren_step_freq", "Siren step frequency (Hz)", int),
        ("siren_tone_duration", "Siren tone duration (ms)", int),
        ("webhook_url", "Webhook URL (empty = disabled)", str),
        ("webhook_type", "Webhook type (none/telegram/slack)", str),
        ("telegram_chat_id", "Telegram chat ID", str),
        ("active_profile", "Profile name", str),
    ]

    while True:
        print()
        print("  Settings")
        print("  " + hr(40))
        for i, (key, label, _) in enumerate(field_config, 1):
            val = getattr(settings, key)
            if isinstance(val, list):
                val = ", ".join(val)
            if key in ("webhook_url",):
                val = val[:50] + "..." if isinstance(val, str) and len(val) > 50 else val
            print(f"  {i:2}. {label}: {val}")
        print("   0. Back")
        print()

        choice = input("  Change #: ").strip()
        if choice == "0":
            break

        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(field_config):
                print("  Invalid choice.")
                input("  Press Enter...")
                continue

            key, label, convert = field_config[idx]
            current = getattr(settings, key)
            if isinstance(current, list):
                current = ", ".join(current)

            new_val = input(f"  {label} [{current}]: ").strip()
            if new_val == "":
                continue

            setattr(settings, key, convert(new_val))
            save_settings(settings)
            print("  Saved.")
        except (ValueError, TypeError) as e:
            print(f"  Error: {e}")
        input("  Press Enter...")

    return settings


def menu_profiles(settings: Settings) -> Settings:
    profiles = load_profiles()

    while True:
        print()
        print("  Profiles")
        print("  " + hr(40))
        for i, (name, cfg) in enumerate(profiles.items(), 1):
            star = " *" if name == settings.active_profile else ""
            print(f"  {i}. {name}{star}  (IDs: {fmt_ids(cfg.customer_ids)})")
        print("   N. New Profile")
        print("   D. Duplicate Profile")
        print("   X. Delete Profile")
        print("   0. Back")
        print()

        choice = input("  > ").strip()
        if choice == "0":
            break
        elif choice.upper() == "N":
            name = input("  Profile name: ").strip()
            if not name:
                print("  Name cannot be empty.")
            elif name in profiles:
                print(f"  Profile '{name}' already exists.")
            else:
                profiles[name] = Settings(active_profile=name)
                save_profiles(profiles)
                settings = profiles[name]
                save_settings(settings)
                print(f"  Created profile: {name}")
        elif choice.upper() == "D":
            if len(profiles) == 0:
                print("  No profiles to duplicate.")
            else:
                print("  Select profile to duplicate:")
                profile_names = list(profiles.keys())
                for i, n in enumerate(profile_names, 1):
                    print(f"    {i}. {n}")
                try:
                    dup_idx = int(input("  > ").strip()) - 1
                    if dup_idx < 0 or dup_idx >= len(profile_names):
                        print("  Invalid choice.")
                    else:
                        src_name = profile_names[dup_idx]
                        new_name = input(f"  New name [{src_name}_copy]: ").strip()
                        if not new_name:
                            new_name = f"{src_name}_copy"
                        profiles[new_name] = Settings.from_dict(profiles[src_name].to_dict())
                        profiles[new_name].active_profile = new_name
                        save_profiles(profiles)
                        print(f"  Duplicated '{src_name}' as '{new_name}'")
                except ValueError:
                    print("  Invalid choice.")
        elif choice.upper() == "X":
            if len(profiles) <= 1:
                print("  Cannot delete the last profile.")
            else:
                print("  Select profile to delete:")
                profile_names = list(profiles.keys())
                for i, n in enumerate(profile_names, 1):
                    suffix = " (active)" if n == settings.active_profile else ""
                    print(f"    {i}. {n}{suffix}")
                try:
                    del_idx = int(input("  > ").strip()) - 1
                    if del_idx < 0 or del_idx >= len(profile_names):
                        print("  Invalid choice.")
                    else:
                        del_name = profile_names[del_idx]
                        confirm = input(f"  Delete '{del_name}'? (y/N): ").strip().lower()
                        if confirm == "y":
                            del profiles[del_name]
                            save_profiles(profiles)
                            if del_name == settings.active_profile:
                                settings = list(profiles.values())[0]
                                settings.active_profile = list(profiles.keys())[0]
                                save_settings(settings)
                            print(f"  Deleted profile: {del_name}")
                        else:
                            print("  Cancelled.")
                except ValueError:
                    print("  Invalid choice.")
        else:
            try:
                idx = int(choice) - 1
                if idx < 0 or idx >= len(profiles):
                    print("  Invalid choice.")
                    input("  Press Enter...")
                    continue

                name = list(profiles.keys())[idx]
                settings = profiles[name]
                settings.active_profile = name
                save_settings(settings)
                print(f"  Switched to profile: {name}")
            except (ValueError, IndexError):
                print("  Invalid choice.")
        input("  Press Enter...")

    return settings


def menu_export() -> None:
    while True:
        print()
        print("  Export")
        print("  " + hr(40))
        print("  1. Export Balance History (CSV)")
        print("  2. Export Margin History (CSV)")
        print("   0. Back")
        print()

        choice = input("  > ").strip()
        if choice == "0":
            break
        elif choice == "1":
            cid = input("  Customer ID (Enter for all): ").strip()
            hours_str = input("  Hours [24]: ").strip()
            hours = int(hours_str) if hours_str else 24
            filename = export_balance_csv(customer_id=cid if cid else None, hours=hours)
            print(f"  Exported to: {filename}")
        elif choice == "2":
            cid = input("  Customer ID (Enter for all): ").strip()
            hours_str = input("  Hours [24]: ").strip()
            hours = int(hours_str) if hours_str else 24
            filename = export_margin_csv(customer_id=cid if cid else None, hours=hours)
            print(f"  Exported to: {filename}")
        else:
            print("  Invalid choice.")
        input("  Press Enter...")


def menu_history() -> None:
    init_db()
    while True:
        print()
        print("  History")
        print("  " + hr(40))
        print("  1. Balance History")
        print("  2. Margin History")
        print("   0. Back")
        print()

        choice = input("  > ").strip()
        if choice == "0":
            break
        elif choice == "1":
            cid = input("  Customer ID (Enter for all): ").strip() or None
            hours_str = input("  Hours [24]: ").strip()
            hours = int(hours_str) if hours_str else 24
            rows = get_balance_history(customer_id=cid, hours=hours, limit=20)
            print()
            print(f"  Balance History ({len(rows)} records)")
            print("  " + hr(60))
            for r in rows:
                print(f"  [{r['recorded_at']}] {r['customer_name']} (ID:{r['customer_id']})  "
                      f"Balance: {r['balance']}  Credit: {r['credit_limit']}  Remaining: {r['remaining']}")
        elif choice == "2":
            cid = input("  Customer ID (Enter for all): ").strip() or None
            hours_str = input("  Hours [24]: ").strip()
            hours = int(hours_str) if hours_str else 24
            rows = get_margin_history(customer_id=cid, hours=hours, limit=20)
            print()
            print(f"  Margin History ({len(rows)} records)")
            print("  " + hr(60))
            for r in rows:
                print(f"  [{r['recorded_at']}] {r['customer_name']} (ID:{r['customer_id']})  "
                      f"Margin: {r['margin']}%  Billed: {r['billed_min']} min")
        else:
            print("  Invalid choice.")
        input("  Press Enter...")


def main() -> None:
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
        print("  Instacall Monitoring Tool  v2.0")
        print("  " + hr(36))
        show_status(settings)
        print("  " + hr(36))
        print("  0. Quick Check - Parallel (Async)")
        print("  1. Start Monitor")
        print("  2. Quick Check - Balances")
        print("  3. Quick Check - Summary")
        print("  4. Quick Check - Full")
        print("  5. Settings")
        print("  6. Profiles")
        print("  7. History")
        print("  8. Export")
        print("  9. Exit")
        print()

        choice = input("  > ").strip()

        if choice == "0":
            run_quick_check_parallel(settings)
        elif choice == "1":
            print()
            print("  Starting continuous monitor...")
            confirm = input("  Press Enter to start (or 0 to cancel): ").strip()
            if confirm == "0":
                continue
            run_monitor(settings)
        elif choice == "2":
            run_quick_check_balance(settings)
        elif choice == "3":
            run_quick_check_summary(settings)
        elif choice == "4":
            run_quick_check_full(settings)
        elif choice == "5":
            settings = menu_settings(settings)
            settings = load_settings()
        elif choice == "6":
            settings = menu_profiles(settings)
        elif choice == "7":
            menu_history()
        elif choice == "8":
            menu_export()
        elif choice == "9":
            print("  Exit.")
            sys.exit(0)
        else:
            print("  Invalid choice.")


if __name__ == "__main__":
    main()
