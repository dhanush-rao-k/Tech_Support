# Tech Support AI Overlay

A local desktop prototype for AI-style tech support guidance with:

1. **Fullscreen overlay instructions** (where to click),
2. **Optional LLM-generated plans**,
3. **Frontend agent actions** ("Do it for me" for supported actions).

## What is new

- Fullscreen always-on-top overlay with spotlight highlight for target regions.
- LLM planner support using an OpenAI-compatible endpoint.
- Agent button (`Do it for me`) to run step actions like `open_url`, `open_app`, and optional `hotkey`.

## Run

```bash
python overlay_assistant.py
```

## LLM setup (optional)

Set environment variables before running:

```bash
export OVERLAY_LLM_URL="https://your-endpoint/v1/chat/completions"
export OVERLAY_LLM_MODEL="gpt-4o-mini"
export OVERLAY_LLM_API_KEY="..."   # optional if your endpoint needs it
```

If LLM is enabled in the UI, the app asks the model to return JSON:

```json
{
  "title": "Task name",
  "description": "Short summary",
  "steps": [
    {
      "instruction": "What to do",
      "target": { "x": 0.3, "y": 0.4, "w": 0.2, "h": 0.1 },
      "actions": [{ "type": "open_url", "value": "https://example.com" }]
    }
  ]
}
```

## Agent actions

Each step can include `actions`:

- `open_url`: opens a browser URL.
- `open_app`: runs a shell command/app launcher.
- `hotkey`: sends key combination like `ctrl+shift+s` (requires optional `pyautogui`).

## Task pack (`tasks.json`)

You can extend/override built-ins by adding `tasks.json` in repo root.

Example:

```json
{
  "reset_password": {
    "title": "Reset Password",
    "description": "Open reset portal and submit request.",
    "steps": [
      {
        "instruction": "Open the reset portal.",
        "actions": [{ "type": "open_url", "value": "https://reset.example.com" }]
      },
      {
        "instruction": "Click Forgot Password.",
        "target": { "x": 0.55, "y": 0.63, "w": 0.17, "h": 0.08 }
      }
    ]
  }
}
```

## Notes

- The overlay is guidance-first and supports optional lightweight automation.
- Desktop automation capabilities vary by OS/window permissions.
