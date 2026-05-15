"""
MigriGuide — Streamlit UI v3
ui/app.py
"""

import streamlit as st
import requests

# ─────────────────────────────────────────────
# PAGE CONFIG  (must be the very first Streamlit call)
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="MigriGuide — Finnish Immigration Assistant",
    page_icon="🇫🇮",
    layout="centered",
    initial_sidebar_state="collapsed",
)

API_URL = "http://127.0.0.1:8000/ask"

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400&display=swap');

html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
.stApp { background-color: #f0f2f6; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 0 !important; padding-bottom: 2rem; max-width: 820px; }

/* Header */
.mg-header {
    background: #003399; padding: 16px 28px 12px;
    margin: -1rem -1rem 0; border-bottom: 3px solid #0040cc;
    display: flex; align-items: center;
    justify-content: space-between; flex-wrap: wrap; gap: 8px;
}
.mg-title { font-size: 1.35rem; font-weight: 600; color: #fff; }
.mg-sub   { font-size: .7rem; color: rgba(255,255,255,.55); font-weight: 300;
            letter-spacing: .5px; text-transform: uppercase; margin-top: 2px; }
.mg-badge { font-size: .68rem; color: rgba(255,255,255,.45);
            font-family: 'IBM Plex Mono', monospace; }

/* Disclaimer */
.mg-disclaimer {
    background: #fff8e1; border-left: 4px solid #f9a825;
    padding: 9px 16px; margin: 14px 0 18px;
    border-radius: 0 6px 6px 0;
    font-size: .79rem; color: #5d4037; line-height: 1.5;
}
.mg-disclaimer a { color: #003399; font-weight: 500; }

/* Chat avatars */
[data-testid="chatAvatarIcon-user"]      { background-color: #003399 !important; }
[data-testid="chatAvatarIcon-assistant"] { background-color: #1a5276 !important; }

/* Chat message wrapper */
[data-testid="stChatMessage"] { background: transparent !important; }

/* Pair divider */
.mg-divider { border: none; border-top: 1px solid #dde3ef; margin: 20px 0 12px; }

/* Topic tag */
.mg-tag {
    display: inline-block; margin-top: 8px; padding: 3px 11px;
    background: #e8edf8; color: #003399; border-radius: 20px;
    font-size: .7rem; font-weight: 600; letter-spacing: .4px;
    text-transform: uppercase;
}

/* Sources expander */
[data-testid="stExpander"] {
    border: 1px solid #dde3ef !important;
    border-radius: 8px !important;
    background: #f7f9fc !important;
    margin-top: 10px !important;
}
[data-testid="stExpander"] summary {
    font-size: .76rem !important; font-weight: 600 !important;
    color: #4a5568 !important; letter-spacing: .3px !important;
}

/* Source row inside expander */
.mg-src-row { display: flex; align-items: baseline; gap: 8px; margin: 5px 0; }
.mg-src-dom {
    background: #e8edf8; color: #003399; border-radius: 3px;
    padding: 1px 6px; font-size: .63rem; font-weight: 700;
    font-family: 'IBM Plex Mono', monospace;
    white-space: nowrap; text-transform: uppercase; flex-shrink: 0;
}
.mg-src-lnk a {
    color: #003399 !important; text-decoration: none;
    font-family: 'IBM Plex Mono', monospace; font-size: .75rem;
}
.mg-src-lnk a:hover { text-decoration: underline; }

/* Follow-up chips label */
.mg-chips-label {
    font-size: .72rem; font-weight: 600; color: #8a94a6;
    letter-spacing: .4px; text-transform: uppercase;
    margin: 16px 0 6px;
}

/* Follow-up chip buttons */
div[data-testid="stButton"].chip > button {
    background: #ffffff !important; color: #003399 !important;
    border: 1.5px solid #c5cee0 !important; border-radius: 20px !important;
    font-size: .8rem !important; padding: 6px 16px !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
    white-space: normal !important; text-align: left !important;
    line-height: 1.4 !important;
}
div[data-testid="stButton"].chip > button:hover {
    background: #e8edf8 !important; border-color: #003399 !important;
}

/* Text input */
[data-testid="stTextInput"] input {
    border: 1.5px solid #c5cee0 !important; border-radius: 8px !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
    font-size: .92rem !important; background: #fff !important; color: #1a202c !important;
}
[data-testid="stTextInput"] input:focus {
    border-color: #003399 !important;
    box-shadow: 0 0 0 3px rgba(0,51,153,.1) !important;
}
[data-testid="stTextInput"] input::placeholder { color: #a0aaba !important; }

/* Send button */
[data-testid="stFormSubmitButton"] button {
    background: #003399 !important; color: #fff !important;
    border: none !important; border-radius: 8px !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
    font-weight: 500 !important; font-size: .9rem !important; height: 44px !important;
}
[data-testid="stFormSubmitButton"] button:hover { background: #002680 !important; }

/* Clear button */
.stButton > button {
    background: transparent !important; color: #8a94a6 !important;
    border: 1px solid #c5cee0 !important; border-radius: 8px !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
    font-size: .8rem !important; padding: 6px 16px !important;
}
.stButton > button:hover { background: #f0f2f6 !important; color: #4a5568 !important; }

/* Empty state */
.mg-empty { text-align: center; padding: 36px 20px 20px; color: #8a94a6; }
.mg-empty-icon  { font-size: 2rem; margin-bottom: 10px; }
.mg-empty-title { font-size: 1rem; font-weight: 500; color: #4a5568; margin-bottom: 8px; }
.mg-empty-body  { font-size: .82rem; line-height: 1.65; max-width: 420px; margin: 0 auto; }

/* Footer */
.mg-footer {
    text-align: center; margin-top: 32px; padding-top: 14px;
    border-top: 1px solid #dde3ef;
    font-size: .7rem; color: #a0aaba;
}
.mg-footer a { color: #003399; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────
for key, default in [
    ("messages",         []),
    ("chat_history",     []),
    ("pending_question", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
CATEGORY_LABELS = {
    "work":                 "💼 Work Permit",
    "family":               "👨‍👩‍👧 Family",
    "study":                "🎓 Study",
    "permanent":            "🏠 Permanent Residence",
    "asylum":               "🛡️ Asylum",
    "temporary_protection": "⛺ Temporary Protection",
    "benefits":             "💶 Benefits / Kela",
    "citizenship":          "🪪 Citizenship",
    "tax":                  "🧾 Tax / Vero",
    "registration":         "📋 Registration",
    "eu_citizen":           "🇪🇺 EU Citizen",
    "appeals":              "⚖️ Appeals",
    "processing":           "⏱️ Processing Time",
    "overstay":             "🚨 Overstay",
    "general":              "ℹ️ General",
}

def _category_label(cat: str) -> str:
    return CATEGORY_LABELS.get(cat, f"🔖 {cat.replace('_', ' ').title()}")


def call_api(question: str, chat_history: list) -> dict:
    """POST to FastAPI. Returns response dict or {"error": message}."""
    try:
        resp = requests.post(
            API_URL,
            json={"question": question, "chat_history": chat_history},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {"error": (
            "🔴 **Cannot reach the MigriGuide API.**\n\n"
            "Make sure Terminal 1 is running:\n```\nuvicorn api.main:app\n```"
        )}
    except requests.exceptions.Timeout:
        return {"error": "⏱️ The request timed out. Please try again."}
    except Exception as e:
        return {"error": f"Unexpected error: {e}"}


def render_sources(sources: list):
    """Render sources as an expander. Uses single-level HTML only — no nesting."""
    if not sources:
        return
    seen, clean = set(), []
    for s in sources:
        url = s.get("url", "")
        if url and url not in seen:
            seen.add(url)
            clean.append(s)
    if not clean:
        return
    with st.expander("📎 Sources cited", expanded=True):
        for s in clean:
            url    = s.get("url", "")
            title  = s.get("title") or url
            domain = s.get("domain", "").upper()
            st.markdown(
                f'<div class="mg-src-row">'
                f'<span class="mg-src-dom">{domain}</span>'
                f'<span class="mg-src-lnk"><a href="{url}" target="_blank">{title}</a></span>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ─────────────────────────────────────────────
# PROCESS PENDING QUESTION
# Runs at the top of every script rerun, before any widgets.
# Both form submits and chip clicks feed into pending_question.
# This single code path handles all question processing.
# ─────────────────────────────────────────────
if st.session_state.pending_question:
    question = st.session_state.pending_question
    st.session_state.pending_question = None

    st.session_state.messages.append({
        "role":    "user",
        "content": question,
    })

    with st.spinner("Searching official sources…"):
        result = call_api(question, st.session_state.chat_history)

    if "error" in result:
        st.session_state.messages.append({
            "role":     "assistant",
            "content":  result["error"],
            "is_error": True,
        })
    else:
        st.session_state.chat_history = result.get(
            "chat_history", st.session_state.chat_history
        )
        st.session_state.messages.append({
            "role":           "assistant",
            "content":        result.get("answer",        "No answer returned."),
            "sources":        result.get("sources",        []),
            "category":       result.get("category",       "general"),
            "low_confidence": result.get("low_confidence", False),
            "follow_ups":     result.get("follow_ups",     []),
            "is_error":       False,
        })

    st.rerun()


# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
st.markdown("""
<div class="mg-header">
    <div>
        <div class="mg-title">🇫🇮 MigriGuide</div>
        <div class="mg-sub">AI-Powered Finnish Immigration Assistant</div>
    </div>
    <div class="mg-badge">Migri · Kela · DVV · Vero · InfoFinland · TE-palvelut · IHH</div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# DISCLAIMER
# ─────────────────────────────────────────────
st.markdown("""
<div class="mg-disclaimer">
    ⚠️ <strong>Unofficial tool — not legal advice.</strong>
    All answers sourced exclusively from official Finnish government websites.
    Always verify at <a href="https://migri.fi" target="_blank">migri.fi</a>
    or consult a licensed immigration lawyer.
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# CONVERSATION DISPLAY
# ─────────────────────────────────────────────
if not st.session_state.messages:
    st.markdown("""
    <div class="mg-empty">
        <div class="mg-empty-icon">🏛️</div>
        <div class="mg-empty-title">What would you like to know?</div>
        <div class="mg-empty-body">
            Ask about work permits, family reunification, permanent residence,
            citizenship, Kela benefits, registration, and more.<br>
            Every answer cites only official government sources.
        </div>
    </div>
    """, unsafe_allow_html=True)

else:
    first_user = True

    for msg in st.session_state.messages:
        role = msg["role"]

        if role == "user":
            # Draw a divider between conversation pairs (not before the first one)
            if not first_user:
                st.markdown('<hr class="mg-divider">', unsafe_allow_html=True)
            first_user = False
            with st.chat_message("user"):
                st.write(msg["content"])

        elif role == "assistant":
            with st.chat_message("assistant"):

                if msg.get("is_error"):
                    st.error(msg["content"])

                else:
                    # Answer text
                    st.markdown(msg["content"])

                    # Topic tag
                    cat = msg.get("category", "")
                    if cat and cat not in ("unknown", "general", ""):
                        st.markdown(
                            f'<div class="mg-tag">{_category_label(cat)}</div>',
                            unsafe_allow_html=True,
                        )

                    # Low confidence warning
                    if msg.get("low_confidence"):
                        st.warning(
                            "⚠️ **Low confidence:** The knowledge base has limited official "
                            "coverage on this specific topic. Please verify directly at "
                            "[migri.fi](https://migri.fi) or call 0295 419 700."
                        )

                    # Sources
                    render_sources(msg.get("sources", []))

    # ── Follow-up chips ──────────────────────
    # Show only for the most recent assistant message
    last_follow_ups = []
    for msg in reversed(st.session_state.messages):
        if msg["role"] == "assistant" and not msg.get("is_error"):
            last_follow_ups = msg.get("follow_ups", [])
            break

    if last_follow_ups:
        st.markdown(
            '<div class="mg-chips-label">💬 You might also ask</div>',
            unsafe_allow_html=True,
        )
        chip_cols = st.columns(len(last_follow_ups))
        for col, chip_text in zip(chip_cols, last_follow_ups):
            with col:
                if st.button(chip_text, key=f"chip_{chip_text}"):
                    st.session_state.pending_question = chip_text
                    st.rerun()


# ─────────────────────────────────────────────
# INPUT FORM
# clear_on_submit=True  →  field empties after every send
# st.form               →  Enter key and Send button both fire exactly once
# ─────────────────────────────────────────────
st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

with st.form("chat_form", clear_on_submit=True):
    col_input, col_send = st.columns([5, 1])
    with col_input:
        user_input = st.text_input(
            "",
            placeholder="Ask about Finnish immigration…",
            label_visibility="collapsed",
        )
    with col_send:
        submitted = st.form_submit_button("Send", use_container_width=True)

# Form submit handler
if submitted and user_input.strip():
    st.session_state.pending_question = user_input.strip()
    st.rerun()


# ─────────────────────────────────────────────
# CLEAR CONVERSATION
# ─────────────────────────────────────────────
if st.session_state.messages:
    col_clr, _ = st.columns([1, 5])
    with col_clr:
        if st.button("🗑️ Clear"):
            st.session_state.messages         = []
            st.session_state.chat_history     = []
            st.session_state.pending_question = None
            st.rerun()


# ─────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────
st.markdown("""
<div class="mg-footer">
    MigriGuide · Unofficial · Not affiliated with Migri or the Finnish government ·
    <a href="https://migri.fi" target="_blank">migri.fi</a>
</div>
""", unsafe_allow_html=True)