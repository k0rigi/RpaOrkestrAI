"""Açık adım risk sözlüğü; yeni katalog türleri testte sınıflandırılmalıdır."""

from __future__ import annotations

from typing import Literal

from ..models import Workflow, walk_steps

Risk = Literal["okuma", "geri_alinamaz"]
READ: Risk = "okuma"
WRITE: Risk = "geri_alinamaz"

# Classify behaviour, not the label: copying a desktop table clicks and changes selection.
STEP_RISKS: dict[str, Risk] = {
    "ai.ask": WRITE,
    "sheets.read_column": READ,
    "desktop.window_write": WRITE,
    "data.sample": READ,
    "core.set": READ,
    "data.append": READ,
    "data.export_csv": WRITE,
    "control.for_each": READ,
    "control.if": READ,
    "core.wait": READ,
    "core.log": READ,
    "database.read": READ,
    "desktop.click": WRITE,
    "desktop.write": WRITE,
    "desktop.hotkey": WRITE,
    "desktop.press": WRITE,
    "desktop.click_template": WRITE,
    "desktop.ocr": READ,
    "desktop.scan_dropdown": WRITE,
    "browser.open": WRITE,
    "browser.fill": WRITE,
    "browser.click": WRITE,
    "browser.text": READ,
    "sheets.read": READ,
    "sheets.write": WRITE,
    "desktop.find_window": READ,
    "desktop.window_click": WRITE,
    "desktop.window_fill": WRITE,
    "desktop.window_key": WRITE,
    "desktop.window_click_key": WRITE,
    "desktop.window_wait_image": READ,
    "window.activate": WRITE,
    "window.read_field": WRITE,
    "window.read_table": WRITE,
    "window.write_table": WRITE,
    "window.text_write": WRITE,
    "window.checkbox": WRITE,
    "window.state": WRITE,
    "window.move": WRITE,
    "window.close": WRITE,
    "window.wait_close": READ,
    "input.mouse_click": WRITE,
    "input.mouse_move": WRITE,
    "input.drag": WRITE,
    "input.scroll": WRITE,
    "input.type": WRITE,
    "input.hotkey": WRITE,
    "input.press": WRITE,
    "input.key_state": WRITE,
    "input.mouse_position": READ,
    "screen.find_image": READ,
    "screen.click_image": WRITE,
    "screen.read_text": READ,
    "screen.wait_text": READ,
    "screen.pixel": READ,
    "screen.screenshot": WRITE,
    "system.open": WRITE,
    "system.run_file": WRITE,
    "system.close_app": WRITE,
    "system.command": WRITE,
    "clipboard.set": WRITE,
    "clipboard.get": READ,
    "file.read_table": READ,
    "file.write_table": WRITE,
    "file.write_cell": WRITE,
    "file.zip": WRITE,
    "file.read_pdf": READ,
    "file.read_text": READ,
    "file.write_text": WRITE,
    "file.exists": READ,
    "file.list": READ,
    "file.operation": WRITE,
    "file.wait": READ,
    "data.calculate": READ,
    "text.transform": READ,
    "data.date": READ,
    "data.list": READ,
    "sheets.read_cell": READ,
    "sheets.read_rows": READ,
    "sheets.write_cell": WRITE,
    "database.query": READ,
    "control.while": READ,
    "control.repeat": READ,
    "control.try": READ,
    "control.break": READ,
    "control.continue": READ,
    "control.goto": READ,
    "control.run_workflow": READ,
    "control.stop": READ,
    "ui.message": WRITE,
    "ui.input": WRITE,
    "web.open": WRITE,
    "web.click": WRITE,
    "web.fill": WRITE,
    "web.read": READ,
    "web.select": WRITE,
    "web.wait": READ,
    "web.press": WRITE,
    "web.navigate": WRITE,
    "web.tab": WRITE,
    "web.read_table": READ,
    "web.download": WRITE,
    "web.upload": WRITE,
    "web.screenshot": WRITE,
    "web.script": WRITE,
    "mail.send": WRITE,
    "http.request": WRITE,
    "database.execute": WRITE,
    # Reading mail or listing a folder only reads; the options below turn the same step into a change.
    "mail.read": READ,
    "ftp.transfer": READ,
    "notify.send": WRITE,
}
# Step options that turn an otherwise reading step into a change: mark mail read, save files, transfer files.
PARAM_WRITES = {
    "mail.read": lambda params: params.get("mark_read") is True or bool(str(params.get("attachment_folder") or "").strip()),
    "ftp.transfer": lambda params: params.get("operation", "download") != "list",
}


def step_risk(action: str, params: dict | None = None) -> Risk:
    risk = STEP_RISKS.get(action, WRITE)
    if risk == READ and action in PARAM_WRITES and PARAM_WRITES[action](params or {}):
        return WRITE
    return risk


def workflow_risk(workflow: Workflow, workflows: dict[str, Workflow] | None = None,
                  _seen: frozenset[str] = frozenset()) -> Risk:
    """Unresolved dependencies and cycles fail closed; policy provides a frozen graph."""
    if workflow.id in _seen:
        return WRITE
    seen = _seen | {workflow.id}
    for step in walk_steps(workflow.steps):
        if step_risk(step.action, step.params) == WRITE:
            return WRITE
        if step.action == "control.run_workflow":
            child = (workflows or {}).get(step.params.get("workflow", ""))
            if child is None or workflow_risk(child, workflows, seen) == WRITE:
                return WRITE
    return READ
