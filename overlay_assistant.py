"""Tech support guidance overlay with optional LLM planning and agent actions."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import messagebox


@dataclass
class Action:
    type: str
    value: str = ""


@dataclass
class Step:
    instruction: str
    target: dict[str, float] | None = None
    actions: list[Action] = field(default_factory=list)


@dataclass
class Task:
    title: str
    description: str
    steps: list[Step]
    source: str = "library"


DEFAULT_TASK_LIBRARY: dict[str, dict] = {
    "wifi": {
        "title": "Connect to Wi-Fi",
        "description": "Guide to connect to a wireless network from quick settings.",
        "steps": [
            {
                "instruction": "Open Quick Settings from the taskbar/system tray.",
                "target": {"x": 0.88, "y": 0.90, "w": 0.11, "h": 0.10},
            },
            {
                "instruction": "Click the Wi-Fi icon to open available networks.",
                "target": {"x": 0.78, "y": 0.64, "w": 0.10, "h": 0.10},
            },
            {"instruction": "Select your network from the list.", "target": {"x": 0.68, "y": 0.36, "w": 0.28, "h": 0.35}},
            {
                "instruction": "Choose Connect and enter your password if prompted.",
                "target": {"x": 0.76, "y": 0.72, "w": 0.14, "h": 0.10},
            },
        ],
    },
    "vpn": {
        "title": "Connect Company VPN",
        "description": "Guide to open VPN settings and connect.",
        "steps": [
            {
                "instruction": "Open your company VPN app.",
                "actions": [{"type": "open_app", "value": ""}],
            },
            {"instruction": "Choose your company profile from the list."},
            {"instruction": "Click Connect and complete MFA if prompted."},
        ],
    },
}

KEYWORDS: dict[str, tuple[str, ...]] = {
    "wifi": ("wifi", "wi-fi", "wireless", "internet", "network"),
    "vpn": ("vpn", "remote", "tunnel", "secure access"),
}


class FrontendAgent:
    """Executes optional actions attached to a step."""

    def execute_step(self, step: Step) -> list[str]:
        if not step.actions:
            return ["No automatic actions on this step."]

        logs: list[str] = []
        for action in step.actions:
            logs.append(self._execute_action(action))
        return logs

    def _execute_action(self, action: Action) -> str:
        if action.type == "open_url":
            webbrowser.open(action.value)
            return f"Opened URL: {action.value}"

        if action.type == "open_app":
            if action.value:
                subprocess.Popen(action.value, shell=True)
                return f"Launched app command: {action.value}"
            return "Skipped open_app: missing command value."

        if action.type == "hotkey":
            try:
                import pyautogui  # type: ignore

                keys = [k.strip() for k in action.value.split("+") if k.strip()]
                if keys:
                    pyautogui.hotkey(*keys)
                    return f"Sent hotkey: {action.value}"
                return "Skipped hotkey: no keys provided."
            except Exception:
                return "Hotkey action requires optional dependency pyautogui."

        return f"Unknown action type: {action.type}"


def _build_task(raw: dict, source: str = "library") -> Task:
    steps = []
    for item in raw["steps"]:
        actions = [Action(type=a["type"], value=a.get("value", "")) for a in item.get("actions", [])]
        steps.append(Step(instruction=item["instruction"], target=item.get("target"), actions=actions))
    return Task(title=raw["title"], description=raw["description"], steps=steps, source=source)


def load_task_library(tasks_file: str = "tasks.json") -> dict[str, Task]:
    raw = dict(DEFAULT_TASK_LIBRARY)
    file_path = Path(tasks_file)
    if file_path.exists():
        with file_path.open("r", encoding="utf-8") as fh:
            incoming = json.load(fh)
        if isinstance(incoming, dict):
            raw.update(incoming)

    return {key: _build_task(value, source="library") for key, value in raw.items()}


def infer_task_key(request: str, keywords: dict[str, tuple[str, ...]] | None = None) -> str | None:
    keyword_map = keywords or KEYWORDS
    text = request.lower().strip()
    if not text:
        return None

    best_key = None
    best_score = 0
    for task_key, words in keyword_map.items():
        score = sum(1 for word in words if word in text)
        if score > best_score:
            best_key = task_key
            best_score = score

    return best_key if best_score else None


def suggest_tasks(request: str, tasks: dict[str, Task]) -> list[str]:
    text = request.lower().strip()
    if not text:
        return list(tasks.keys())

    ranked: list[tuple[int, str]] = []
    for key, task in tasks.items():
        bag = f"{key} {task.title} {task.description}".lower()
        score = sum(1 for token in text.split() if token in bag)
        ranked.append((score, key))

    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [k for score, k in ranked if score > 0] or list(tasks.keys())


def _extract_json_blob(content: str) -> dict | None:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?", "", content).strip()
        content = re.sub(r"```$", "", content).strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def generate_task_from_llm(user_request: str) -> Task | None:
    """Uses an OpenAI-compatible endpoint if env vars are configured.

    Required environment:
      OVERLAY_LLM_URL, OVERLAY_LLM_MODEL
    Optional:
      OVERLAY_LLM_API_KEY
    """

    endpoint = os.getenv("OVERLAY_LLM_URL", "").strip()
    model = os.getenv("OVERLAY_LLM_MODEL", "").strip()
    api_key = os.getenv("OVERLAY_LLM_API_KEY", "").strip()

    if not endpoint or not model:
        return None

    schema_hint = {
        "title": "Task title",
        "description": "Short explanation",
        "steps": [
            {
                "instruction": "What user should do",
                "target": {"x": 0.3, "y": 0.3, "w": 0.2, "h": 0.1},
                "actions": [{"type": "open_url", "value": "https://example.com"}],
            }
        ],
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a tech support planner. Return JSON only with title, description, steps[]. Keep coordinates normalized 0..1.",
            },
            {
                "role": "user",
                "content": f"Create a UI guidance plan for: {user_request}\nJSON schema sample: {json.dumps(schema_hint)}",
            },
        ],
        "temperature": 0.2,
    }

    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None

    content = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    blob = _extract_json_blob(content)
    if not blob or "steps" not in blob:
        return None

    try:
        return _build_task(blob, source="llm")
    except (KeyError, TypeError):
        return None


class OverlayUI:
    def __init__(self, root: tk.Tk, task: Task) -> None:
        self.root = root
        self.task = task
        self.step_index = 0
        self.agent = FrontendAgent()
        self.status_message = ""

        self.width = self.root.winfo_screenwidth()
        self.height = self.root.winfo_screenheight()

        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.95)
        self.root.configure(bg="#0E1220")

        self.canvas = tk.Canvas(self.root, bg="#0E1220", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.next_btn = tk.Button(self.root, text="Next ▶", command=self.next_step, font=("Segoe UI", 12, "bold"))
        self.prev_btn = tk.Button(self.root, text="◀ Previous", command=self.prev_step, font=("Segoe UI", 12, "bold"))
        self.close_btn = tk.Button(self.root, text="✕ Close", command=self.root.destroy, font=("Segoe UI", 12, "bold"))
        self.agent_btn = tk.Button(self.root, text="Do it for me", command=self.run_agent_for_step, font=("Segoe UI", 12, "bold"))

        self.root.bind("<Escape>", lambda _: self.root.destroy())
        self.root.bind("<Right>", lambda _: self.next_step())
        self.root.bind("<Left>", lambda _: self.prev_step())

        self.render()

    def run_agent_for_step(self) -> None:
        logs = self.agent.execute_step(self.task.steps[self.step_index])
        self.status_message = " | ".join(logs)
        self.render()

    def draw_instruction_panel(self) -> None:
        panel_x, panel_y = 36, 36
        panel_w, panel_h = 760, 300
        self.canvas.create_rectangle(panel_x, panel_y, panel_x + panel_w, panel_y + panel_h, fill="#1A2238", outline="#6EC1FF", width=2)

        step = self.task.steps[self.step_index]
        self.canvas.create_text(panel_x + 20, panel_y + 24, text=self.task.title, fill="#EAF3FF", anchor="nw", font=("Segoe UI", 18, "bold"))
        self.canvas.create_text(
            panel_x + 20,
            panel_y + 62,
            text=f"{self.task.description}  • source: {self.task.source}",
            fill="#BED3EE",
            anchor="nw",
            font=("Segoe UI", 11),
            width=panel_w - 40,
        )

        step_label = f"Step {self.step_index + 1}/{len(self.task.steps)}"
        self.canvas.create_text(panel_x + 20, panel_y + 120, text=step_label, fill="#9ACBFF", anchor="nw", font=("Segoe UI", 11, "bold"))
        self.canvas.create_text(panel_x + 20, panel_y + 148, text=step.instruction, fill="#FFFFFF", anchor="nw", font=("Segoe UI", 14), width=panel_w - 40)

        if self.status_message:
            self.canvas.create_text(panel_x + 20, panel_y + 240, text=f"Agent: {self.status_message}", fill="#8EF5B6", anchor="nw", font=("Segoe UI", 10), width=panel_w - 40)

    def draw_target(self, target: dict[str, float] | None) -> None:
        if not target:
            return

        x = int(target["x"] * self.width)
        y = int(target["y"] * self.height)
        w = int(target["w"] * self.width)
        h = int(target["h"] * self.height)

        self.canvas.create_rectangle(0, 0, self.width, y, fill="#0B0F1A", outline="", stipple="gray50")
        self.canvas.create_rectangle(0, y + h, self.width, self.height, fill="#0B0F1A", outline="", stipple="gray50")
        self.canvas.create_rectangle(0, y, x, y + h, fill="#0B0F1A", outline="", stipple="gray50")
        self.canvas.create_rectangle(x + w, y, self.width, y + h, fill="#0B0F1A", outline="", stipple="gray50")

        self.canvas.create_rectangle(x, y, x + w, y + h, outline="#FFD166", width=5)
        self.canvas.create_rectangle(x - 8, y - 8, x + w + 8, y + h + 8, outline="#FF8A00", width=2, dash=(8, 6))
        self.canvas.create_text(x + w // 2, max(24, y - 28), text="Go here", fill="#FFD166", font=("Segoe UI", 12, "bold"))

    def render(self) -> None:
        self.canvas.delete("all")
        self.draw_target(self.task.steps[self.step_index].target)
        self.draw_instruction_panel()

        self.canvas.create_window(self.width - 120, 45, window=self.close_btn)
        self.canvas.create_window(self.width - 120, self.height - 45, window=self.next_btn)
        self.canvas.create_window(self.width - 260, self.height - 45, window=self.prev_btn)
        self.canvas.create_window(self.width - 430, self.height - 45, window=self.agent_btn)

        self.prev_btn.configure(state=(tk.DISABLED if self.step_index == 0 else tk.NORMAL))

        if self.step_index >= len(self.task.steps) - 1:
            self.next_btn.configure(text="Done", command=self.root.destroy)
        else:
            self.next_btn.configure(text="Next ▶", command=self.next_step)

        self.canvas.create_text(
            self.width // 2,
            self.height - 24,
            text="ESC: close • ←/→: previous/next • Do it for me: run step action",
            fill="#9BB1CC",
            font=("Segoe UI", 10),
        )

    def next_step(self) -> None:
        if self.step_index < len(self.task.steps) - 1:
            self.step_index += 1
            self.status_message = ""
            self.render()

    def prev_step(self) -> None:
        if self.step_index > 0:
            self.step_index -= 1
            self.status_message = ""
            self.render()


def launch_overlay(task: Task) -> None:
    overlay = tk.Tk()
    OverlayUI(overlay, task)
    overlay.mainloop()


def start_prompt() -> None:
    tasks = load_task_library()

    prompt = tk.Tk()
    prompt.title("Tech Support AI Overlay")
    prompt.geometry("680x420")
    prompt.configure(bg="#1C243A")

    title = tk.Label(prompt, text="What do you want help with?", bg="#1C243A", fg="#F4F8FF", font=("Segoe UI", 16, "bold"))
    title.pack(pady=(20, 8))

    hint = tk.Label(
        prompt,
        text='Examples: "connect to vpn", "connect to wifi". Enable LLM to generate a custom flow.',
        bg="#1C243A",
        fg="#B8C9E1",
        font=("Segoe UI", 10),
    )
    hint.pack()

    entry = tk.Entry(prompt, width=66, font=("Segoe UI", 12))
    entry.pack(pady=12)

    llm_var = tk.BooleanVar(value=True)
    llm_toggle = tk.Checkbutton(
        prompt,
        text="Use LLM planner (requires OVERLAY_LLM_URL and OVERLAY_LLM_MODEL)",
        variable=llm_var,
        bg="#1C243A",
        fg="#D7E6FF",
        selectcolor="#1C243A",
        activebackground="#1C243A",
        activeforeground="#D7E6FF",
    )
    llm_toggle.pack()

    listbox = tk.Listbox(prompt, height=6, width=60, font=("Segoe UI", 11))
    listbox.pack(pady=(8, 8))

    status = tk.Label(prompt, text="", bg="#1C243A", fg="#FFB4B4", font=("Segoe UI", 10, "bold"), wraplength=630)
    status.pack(pady=(2, 0))

    def refresh_suggestions() -> None:
        listbox.delete(0, tk.END)
        for key in suggest_tasks(entry.get(), tasks)[:6]:
            listbox.insert(tk.END, f"{tasks[key].title}  [{key}]")

    def selected_task_key() -> str | None:
        selection = listbox.curselection()
        if selection:
            text = listbox.get(selection[0])
            return text.split("[")[-1].rstrip("]")
        return infer_task_key(entry.get())

    def on_start() -> None:
        query = entry.get().strip()
        if not query:
            status.config(text="Please enter a request.")
            return

        if llm_var.get():
            llm_task = generate_task_from_llm(query)
            if llm_task:
                prompt.destroy()
                launch_overlay(llm_task)
                return
            status.config(text="LLM unavailable or returned invalid JSON. Falling back to local library.")

        task_key = selected_task_key()
        if not task_key or task_key not in tasks:
            status.config(text="Task not recognized yet. Add tasks in tasks.json, pick a suggestion, or enable LLM.")
            return

        prompt.destroy()
        launch_overlay(tasks[task_key])

    go_button = tk.Button(prompt, text="Start Fullscreen Guidance", command=on_start, font=("Segoe UI", 12, "bold"))
    go_button.pack(pady=8)

    entry.focus_set()
    entry.bind("<KeyRelease>", lambda _: refresh_suggestions())
    prompt.bind("<Return>", lambda _: on_start())
    listbox.bind("<Double-Button-1>", lambda _: on_start())

    refresh_suggestions()
    prompt.mainloop()


if __name__ == "__main__":
    try:
        start_prompt()
    except Exception as exc:
        messagebox.showerror("Tech Support AI Overlay", f"Application error: {exc}")
