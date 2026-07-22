from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Optional

from flask import Flask, jsonify, redirect, render_template, request, url_for

from config import (
    SETTINGS_FILE,
    STATUS_FILE,
    Settings,
    load_profiles,
    load_settings,
    save_profiles,
    save_settings,
    validate_settings,
)

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True

_monitor_thread: Optional[threading.Thread] = None
_stop_event: Optional[threading.Event] = None
_monitor_running: bool = False


def _read_status() -> dict[str, Any]:
    try:
        with open(STATUS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"alive": False, "error": "status file not found"}


def _get_running_status() -> dict[str, Any]:
    status = _read_status()
    status["web_running"] = _monitor_running
    return status


@app.route("/admin")
def dashboard():
    status = _get_running_status()
    settings = load_settings()
    return render_template("dashboard.html", status=status, settings=settings)


@app.route("/admin/status")
def admin_status():
    return jsonify(_get_running_status())


@app.route("/admin/start", methods=["POST"])
def admin_start():
    global _monitor_thread, _stop_event, _monitor_running

    if _monitor_running:
        return redirect(url_for("dashboard"))

    from monitor import run_monitor

    settings = load_settings()
    _stop_event = threading.Event()
    _monitor_thread = threading.Thread(
        target=run_monitor, args=(settings, _stop_event), daemon=True, name="monitor-thread"
    )
    _monitor_thread.start()
    _monitor_running = True
    logging.info("Monitor started via web admin.")
    return redirect(url_for("dashboard"))


@app.route("/admin/stop", methods=["POST"])
def admin_stop():
    global _monitor_running, _stop_event

    if _monitor_running and _stop_event is not None:
        _stop_event.set()
        _monitor_running = False
        logging.info("Monitor stop requested via web admin.")
    return redirect(url_for("dashboard"))


@app.route("/admin/settings", methods=["GET", "POST"])
def admin_settings():
    if request.method == "POST":
        form = request.form
        settings = load_settings()

        settings.customer_ids = [x.strip() for x in form.get("customer_ids", "18").split(",") if x.strip()]

        int_fields = [
            "check_interval_seconds", "db_retention_days", "request_timeout",
            "siren_loops", "siren_min_freq", "siren_max_freq", "siren_step_freq",
            "siren_tone_duration", "alert_cooldown_seconds", "health_port", "webadmin_port",
        ]
        for key in int_fields:
            if form.get(key):
                setattr(settings, key, int(form[key]))

        float_fields = [
            "balance_threshold", "balance_rearm_threshold", "margin_threshold",
            "margin_rearm_threshold", "billed_min_threshold",
        ]
        for key in float_fields:
            if form.get(key):
                setattr(settings, key, float(form[key]))

        bool_fields = ["audio_enabled", "logging_json", "summary_show_all"]
        for key in bool_fields:
            setattr(settings, key, key in form)

        str_fields = [
            "summary_direction", "summary_interval", "webhook_url", "webhook_type",
            "telegram_chat_id", "active_hours_start", "active_hours_end", "active_days",
            "active_profile",
        ]
        for key in str_fields:
            if form.get(key) is not None:
                setattr(settings, key, form[key])

        errors = validate_settings(settings)
        if errors:
            return render_template("settings.html", settings=load_settings(), errors=errors)

        save_settings(settings)
        return redirect(url_for("dashboard"))

    return render_template("settings.html", settings=load_settings(), errors=None)


@app.route("/admin/profiles", methods=["GET", "POST"])
def admin_profiles():
    profiles = load_profiles()
    settings = load_settings()
    message: Optional[str] = None

    if request.method == "POST":
        action = request.form.get("action", "")
        try:
            if action == "switch":
                name = request.form["name"]
                if name in profiles:
                    settings = profiles[name]
                    settings.active_profile = name
                    save_settings(settings)
                    message = f"Switched to profile: {name}"
            elif action == "create":
                name = request.form.get("new_name", "").strip()
                if name and name not in profiles:
                    profiles[name] = Settings(active_profile=name)
                    save_profiles(profiles)
                    message = f"Created profile: {name}"
                else:
                    message = "Name empty or already exists." if name else "Name cannot be empty."
            elif action == "duplicate":
                src = request.form["source"]
                new_name = request.form.get("dup_name", "").strip() or f"{src}_copy"
                if src in profiles and new_name not in profiles:
                    profiles[new_name] = Settings.from_dict(profiles[src].to_dict())
                    profiles[new_name].active_profile = new_name
                    save_profiles(profiles)
                    message = f"Duplicated '{src}' as '{new_name}'"
                else:
                    message = "Duplicate failed (name exists or source not found)."
            elif action == "delete":
                name = request.form["name"]
                if len(profiles) > 1 and name in profiles:
                    del profiles[name]
                    if name == settings.active_profile:
                        first = list(profiles.keys())[0]
                        settings = profiles[first]
                        settings.active_profile = first
                        save_settings(settings)
                    save_profiles(profiles)
                    message = f"Deleted profile: {name}"
                else:
                    message = "Cannot delete last profile or profile not found."
        except (KeyError, ValueError) as e:
            message = f"Error: {e}"

        profiles = load_profiles()
        settings = load_settings()

    return render_template(
        "profiles.html",
        profiles=profiles,
        active_profile=settings.active_profile,
        message=message,
    )


def start_webadmin(port: int) -> None:
    tpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
    app.template_folder = tpl_dir

    def _run():
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

    thread = threading.Thread(target=_run, daemon=True, name="webadmin-server")
    thread.start()
    logging.info(f"Web admin started on http://0.0.0.0:{port}/admin")
