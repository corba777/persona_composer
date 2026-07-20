"""Minimal zinc / DM Sans styling for the playground."""

from __future__ import annotations


def inject_css(*, dark: bool = False) -> str:
    bg = "#09090b" if dark else "#ffffff"
    bg_subtle = "#0c0c0f" if dark else "#f9fafb"
    card = "#0c0c0f" if dark else "#ffffff"
    border = "#1e1e24" if dark else "#e4e4e7"
    text = "#fafafa" if dark else "#09090b"
    text_muted = "#71717a"
    accent = "#2563eb"

    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

header[data-testid="stHeader"], #MainMenu, footer, [data-testid="stToolbar"],
[data-testid="stDecoration"], [data-testid="stStatusWidget"], .stDeployButton {{
    display: none !important;
}}

html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"], .main,
.block-container, section[data-testid="stMain"] {{
    background-color: {bg} !important;
    color: {text} !important;
    font-family: 'DM Sans', -apple-system, sans-serif !important;
}}

.block-container {{
    padding: 1.5rem 2rem 2.5rem !important;
    max-width: 1400px !important;
}}

h1, h2, h3, h4 {{
    font-family: 'DM Sans', sans-serif !important;
    letter-spacing: -0.02em !important;
    color: {text} !important;
}}

[data-testid="stSidebar"] {{
    background: {bg_subtle} !important;
    border-right: 1px solid {border} !important;
}}

.pc-card {{
    background: {card};
    border: 1px solid {border};
    border-radius: 10px;
    padding: 1rem 1.15rem;
    margin-bottom: 0.75rem;
}}

.pc-muted {{
    color: {text_muted};
    font-size: 0.875rem;
}}

.pc-mono {{
    font-family: 'JetBrains Mono', ui-monospace, monospace !important;
    font-size: 0.78rem !important;
}}

.pc-brand {{
    font-size: 1.35rem;
    font-weight: 700;
    letter-spacing: -0.03em;
}}

.pc-accent {{
    color: {accent};
}}

div[data-testid="stCodeBlock"] pre {{
    font-family: 'JetBrains Mono', ui-monospace, monospace !important;
    font-size: 0.75rem !important;
}}
</style>
"""
