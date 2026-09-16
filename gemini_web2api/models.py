"""Model definitions and mapping from Gemini frontend JS source."""

# MODE_CATEGORY enum from 028-6eb337387583.js:
#   1=FAST, 2=THINKING, 3=PRO, 4=AUTO, 5=FAST_DYNAMIC_THINKING, 6=FLASH_LITE

MODELS = {
    "gemini-3.8-flash": {
        "mode": 1, "think": 4,
        "desc": "Google's default all-around model (Gemini 3.8 Flash)",
    },
    "gemini-3.8-flash-thinking": {
        "mode": 2, "think": 0,
        "desc": "Gemini 3.8 Flash with Extended Thinking",
    },
    "gemini-3.5-flash-lite": {
        "mode": 6, "think": 4,
        "desc": "Fastest lightweight model (Gemini 3.5 Flash-Lite)",
    },
    "gemini-3.1-pro": {
        "mode": 3, "think": 4, "extra": {31: 2, 80: 3},
        "desc": "Advanced reasoning model (Gemini 3.1 Pro - Requires Gemini Advanced)",
    },
    "gemini-3.1-pro-thinking": {
        "mode": 3, "think": 0, "extra": {31: 2, 80: 3},
        "desc": "Gemini 3.1 Pro with Extended Thinking (Requires Gemini Advanced)",
    },
    "gemini-auto": {
        "mode": 4, "think": 4,
        "desc": "Auto model selection",
    },
    # Backward compatibility aliases
    "gemini-3.7-flash": {
        "mode": 1, "think": 4,
        "desc": "Alias for Gemini 3.8 Flash",
    },
    "gemini-3.6-flash": {
        "mode": 1, "think": 4,
        "desc": "Alias for Gemini 3.8 Flash",
    },
    "gemini-3.5-flash": {
        "mode": 1, "think": 4,
        "desc": "Alias for Gemini 3.8 Flash",
    },
    "gemini-3.5-flash-thinking": {
        "mode": 2, "think": 0,
        "desc": "Alias for Gemini 3.8 Flash with Extended Thinking",
    },
    "gemini-flash-lite": {
        "mode": 6, "think": 4,
        "desc": "Alias for Gemini 3.5 Flash-Lite",
    },
    # OpenAI drop-in aliases for clients with hardcoded model selectors
    "gpt-4o": {
        "mode": 2, "think": 0,
        "desc": "Drop-in alias -> Gemini 3.8 Flash Thinking",
    },
    "gpt-4": {
        "mode": 2, "think": 0,
        "desc": "Drop-in alias -> Gemini 3.8 Flash Thinking",
    },
    "gpt-3.5-turbo": {
        "mode": 1, "think": 4,
        "desc": "Drop-in alias -> Gemini 3.8 Flash",
    },
}


def resolve_model(model_name: str, default: str = "gemini-3.8-flash"):
    """Resolve model name to (name, mode_id, think_mode, error, extra_fields).

    Unknown model names fall back to default rather than erroring,
    since upstream clients may request arbitrary model identifiers.
    """
    think_override = None
    if "@think=" in model_name:
        model_name, think_str = model_name.rsplit("@think=", 1)
        try:
            think_override = int(think_str)
        except ValueError:
            return None, None, None, f"Invalid think level: {think_str}", None
    cfg = MODELS.get(model_name)
    if not cfg:
        from .gemini import log
        log(f"Unknown model '{model_name}', falling back to '{default}'")
        model_name = default
        cfg = MODELS[default]
    mode_id = cfg["mode"]
    think_mode = think_override if think_override is not None else cfg["think"]
    if think_override == 0 and mode_id == 1:
        mode_id = 2
    extra = cfg.get("extra")
    return model_name, mode_id, think_mode, None, extra
