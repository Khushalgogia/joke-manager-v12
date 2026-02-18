"""
Joke Manager — Streamlit Edition (V12-Aligned)
Manage jokes, generate campaigns, and explore your comedy database.
"""

import os
import re
import json
import time
import pandas as pd
import streamlit as st
from openai import OpenAI
from supabase import create_client
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi

# ─── Config & Setup ──────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Joke Manager",
    page_icon="🎭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS — Vibrant Animated Design
st.markdown("""
<style>
    /* ─── Animated Gradient Background ─── */
    .stApp {
        background: linear-gradient(-45deg, #0d0221, #150734, #1a0a3e, #0c0626, #1b0b40);
        background-size: 400% 400%;
        animation: gradientShift 15s ease infinite;
        color: #f0f0ff;
        min-height: 100vh;
    }
    @keyframes gradientShift {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }

    /* ─── Floating Bubbles (injected via HTML divs) ─── */
    .bubble-container {
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        pointer-events: none;
        z-index: 0;
        overflow: hidden;
    }
    .bubble {
        position: absolute;
        border-radius: 50%;
        opacity: 0;
        animation: floatUp linear infinite;
    }
    @keyframes floatUp {
        0% { transform: translateY(100vh) scale(0.3); opacity: 0; }
        10% { opacity: 0.6; }
        50% { opacity: 0.4; }
        90% { opacity: 0.1; }
        100% { transform: translateY(-100px) scale(1.2); opacity: 0; }
    }

    /* ─── All Content Above Bubbles ─── */
    .stApp > * { position: relative; z-index: 1; }
    section[data-testid="stSidebar"] > * { position: relative; z-index: 1; }

    /* ─── Typography ─── */
    h1, h2, h3, h4, h5, h6 {
        color: #ffffff !important;
        text-shadow: 0 0 20px rgba(138, 43, 226, 0.3);
    }
    h1 { 
        background: linear-gradient(90deg, #ff6ec7, #7b68ee, #00d4ff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: 2.5rem !important;
        font-weight: 800 !important;
    }
    p, span, label, .stMarkdown, li {
        color: #e8e8ff !important;
    }

    /* ─── Glassmorphism Cards / Containers ─── */
    [data-testid="stVerticalBlock"] > div[data-testid="stHorizontalBlock"] {
        position: relative; z-index: 1;
    }
    div[data-testid="stExpander"] {
        background: rgba(255, 255, 255, 0.04) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 12px;
        backdrop-filter: blur(10px);
    }
    div[data-testid="column"] {
        position: relative; z-index: 1;
    }
    /* Bordered containers (st.container(border=True)) */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(20, 10, 50, 0.6) !important;
        border: 1px solid rgba(138, 43, 226, 0.3) !important;
        border-radius: 16px !important;
        backdrop-filter: blur(12px) !important;
        box-shadow: 0 4px 30px rgba(138, 43, 226, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.05);
        transition: all 0.3s ease;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: rgba(0, 212, 255, 0.5) !important;
        box-shadow: 0 8px 40px rgba(0, 212, 255, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.08);
        transform: translateY(-2px);
    }

    /* ─── Buttons — Neon Glow ─── */
    .stButton > button {
        width: 100%;
        border-radius: 12px !important;
        height: 3em;
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        color: #ffffff !important;
        background: linear-gradient(135deg, #7b2ff7 0%, #c41cff 50%, #ff6ec7 100%) !important;
        border: none !important;
        box-shadow: 0 0 15px rgba(196, 28, 255, 0.3), 0 4px 15px rgba(0,0,0,0.2) !important;
        transition: all 0.3s ease !important;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .stButton > button:hover {
        box-shadow: 0 0 30px rgba(196, 28, 255, 0.5), 0 0 60px rgba(123, 47, 247, 0.2), 0 6px 20px rgba(0,0,0,0.3) !important;
        transform: translateY(-2px) scale(1.02);
    }
    .stButton > button:active {
        transform: translateY(0px) scale(0.98);
    }
    /* Primary button override */
    button[kind="primary"] {
        background: linear-gradient(135deg, #00d4ff 0%, #7b68ee 50%, #ff6ec7 100%) !important;
        box-shadow: 0 0 20px rgba(0, 212, 255, 0.4), 0 4px 15px rgba(0,0,0,0.2) !important;
    }
    button[kind="primary"]:hover {
        box-shadow: 0 0 40px rgba(0, 212, 255, 0.6), 0 0 80px rgba(123, 104, 238, 0.2) !important;
    }

    /* ─── Inputs ─── */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stSelectbox > div > div {
        background: rgba(20, 10, 50, 0.7) !important;
        color: #ffffff !important;
        border: 1px solid rgba(138, 43, 226, 0.4) !important;
        border-radius: 10px !important;
        transition: all 0.3s ease;
    }
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: #00d4ff !important;
        box-shadow: 0 0 15px rgba(0, 212, 255, 0.3) !important;
    }
    .stTextInput > div > div > input::placeholder,
    .stTextArea > div > div > textarea::placeholder {
        color: rgba(200, 200, 255, 0.4) !important;
    }

    /* ─── Sidebar ─── */
    section[data-testid="stSidebar"] {
        background: rgba(10, 5, 30, 0.95) !important;
        border-right: 1px solid rgba(138, 43, 226, 0.2) !important;
    }
    section[data-testid="stSidebar"] .stMarkdown p {
        color: #d0d0ff !important;
    }

    /* ─── Tabs ─── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: rgba(20, 10, 50, 0.5);
        border-radius: 16px;
        padding: 6px;
        border: 1px solid rgba(138, 43, 226, 0.2);
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 12px !important;
        color: #b0b0ff !important;
        font-weight: 600 !important;
        padding: 8px 20px !important;
        transition: all 0.3s ease;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, rgba(123, 47, 247, 0.4), rgba(0, 212, 255, 0.3)) !important;
        color: #ffffff !important;
        box-shadow: 0 0 15px rgba(123, 47, 247, 0.3);
    }
    .stTabs [data-baseweb="tab-highlight"] {
        background-color: transparent !important;
    }
    .stTabs [data-baseweb="tab-border"] {
        display: none;
    }

    /* ─── Metrics ─── */
    [data-testid="stMetric"] {
        background: rgba(20, 10, 50, 0.6) !important;
        border: 1px solid rgba(0, 212, 255, 0.2) !important;
        border-radius: 12px;
        padding: 12px !important;
        backdrop-filter: blur(8px);
    }
    [data-testid="stMetricValue"] {
        color: #00d4ff !important;
        font-weight: 700 !important;
        text-shadow: 0 0 10px rgba(0, 212, 255, 0.3);
    }
    [data-testid="stMetricLabel"] {
        color: #c0c0ff !important;
    }

    /* ─── Alerts ─── */
    .stSuccess {
        background: rgba(0, 200, 100, 0.15) !important;
        border: 1px solid rgba(0, 255, 128, 0.3) !important;
        color: #00ff80 !important;
        border-radius: 12px;
    }
    .stError {
        background: rgba(255, 50, 80, 0.15) !important;
        border: 1px solid rgba(255, 80, 100, 0.3) !important;
        color: #ff6b6b !important;
        border-radius: 12px;
    }
    .stWarning {
        background: rgba(255, 200, 0, 0.1) !important;
        border: 1px solid rgba(255, 215, 0, 0.3) !important;
        color: #ffd700 !important;
        border-radius: 12px;
    }
    .stInfo {
        background: rgba(0, 150, 255, 0.1) !important;
        border: 1px solid rgba(0, 180, 255, 0.3) !important;
        color: #00b4ff !important;
        border-radius: 12px;
    }

    /* ─── Progress Bar ─── */
    .stProgress > div > div > div {
        background: linear-gradient(90deg, #7b2ff7, #00d4ff, #ff6ec7) !important;
        border-radius: 8px;
    }

    /* ─── Data Editor / Dataframes ─── */
    [data-testid="stDataFrame"], .stDataFrame {
        border: 1px solid rgba(138, 43, 226, 0.3) !important;
        border-radius: 12px;
        overflow: hidden;
    }

    /* ─── Divider ─── */
    hr {
        border-color: rgba(138, 43, 226, 0.3) !important;
        margin: 1.5rem 0 !important;
    }

    /* ─── Select Slider ─── */
    .stSlider > div {
        color: #c0c0ff !important;
    }

    /* ─── Caption text ─── */
    .stCaption, small {
        color: #9090cc !important;
    }

    /* ─── Status widget ─── */
    [data-testid="stStatusWidget"] {
        background: rgba(20, 10, 50, 0.7) !important;
        border: 1px solid rgba(138, 43, 226, 0.3) !important;
        border-radius: 12px;
        backdrop-filter: blur(8px);
    }

    /* ─── Popover ─── */
    [data-testid="stPopover"] {
        background: rgba(20, 10, 50, 0.95) !important;
        border: 1px solid rgba(138, 43, 226, 0.3) !important;
        border-radius: 12px;
        backdrop-filter: blur(15px);
    }
    /* Popover panel (the floating content) */
    [data-testid="stPopoverBody"],
    div[data-baseweb="popover"] > div {
        background: rgba(15, 8, 40, 0.98) !important;
        border: 1px solid rgba(138, 43, 226, 0.4) !important;
        border-radius: 12px !important;
        backdrop-filter: blur(20px) !important;
    }
    [data-testid="stPopoverBody"] p,
    [data-testid="stPopoverBody"] span,
    [data-testid="stPopoverBody"] label,
    div[data-baseweb="popover"] p,
    div[data-baseweb="popover"] span,
    div[data-baseweb="popover"] label {
        color: #e8e8ff !important;
    }
    [data-testid="stPopoverBody"] textarea,
    div[data-baseweb="popover"] textarea {
        background: rgba(20, 10, 50, 0.8) !important;
        color: #ffffff !important;
        border: 1px solid rgba(138, 43, 226, 0.5) !important;
    }

    /* ─── Checkbox ─── */
    .stCheckbox label span {
        color: #e8e8ff !important;
    }

    /* ─── Scrollbar ─── */
    ::-webkit-scrollbar { width: 8px; }
    ::-webkit-scrollbar-track { background: rgba(10, 5, 30, 0.5); }
    ::-webkit-scrollbar-thumb {
        background: linear-gradient(180deg, #7b2ff7, #00d4ff);
        border-radius: 4px;
    }
</style>
""", unsafe_allow_html=True)

# ─── Inject animated bubble divs ─────────────────────────────────────────────
import random as _rng
_bubble_colors = [
    'rgba(255, 0, 128, 0.25)', 'rgba(0, 200, 255, 0.2)', 'rgba(138, 43, 226, 0.3)',
    'rgba(255, 215, 0, 0.2)', 'rgba(0, 255, 200, 0.15)', 'rgba(255, 100, 200, 0.2)',
    'rgba(100, 149, 237, 0.2)', 'rgba(0, 255, 128, 0.15)', 'rgba(200, 100, 255, 0.2)',
]
_bubbles_html = '<div class="bubble-container">'
for _i in range(20):
    _size = _rng.randint(15, 80)
    _left = _rng.randint(0, 100)
    _dur = _rng.uniform(8, 20)
    _delay = _rng.uniform(0, 15)
    _color = _rng.choice(_bubble_colors)
    _bubbles_html += f'<div class="bubble" style="width:{_size}px;height:{_size}px;left:{_left}%;background:{_color};animation-duration:{_dur:.1f}s;animation-delay:{_delay:.1f}s;"></div>'
_bubbles_html += '</div>'
st.markdown(_bubbles_html, unsafe_allow_html=True)


# ─── Clients ─────────────────────────────────────────────────────────────────

# Load secrets (Streamlit Cloud or local .env)
# Try loading local .env if secrets not found
try:
    load_dotenv()
except:
    pass

def get_openai_client():
    api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.error("❌ OPENAI_API_KEY not found in secrets or environment.")
        st.stop()
    return OpenAI(api_key=api_key)

def get_supabase_client():
    url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        st.error("❌ SUPABASE_URL/KEY not found in secrets or environment.")
        st.stop()
    return create_client(url, key)

def get_gemini_client():
    api_key = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        st.warning("⚠️ GEMINI_API_KEY not found. V12 generation disabled.")
        return None
    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except Exception as e:
        st.warning(f"⚠️ Gemini init failed: {e}")
        return None

openai_client = get_openai_client()
supabase = get_supabase_client()
gemini_client = get_gemini_client()


# ─── Helper Functions ────────────────────────────────────────────────────────

def get_embedding(text):
    """Generate embedding for text using OpenAI."""
    text = text.replace("\n", " ").strip()
    if not text:
        return None
    try:
        response = openai_client.embeddings.create(
            input=[text],
            model="text-embedding-3-small"
        )
        return response.data[0].embedding
    except Exception as e:
        st.error(f"Embedding failed: {e}")
        return None

def create_joke_bridge(joke_text):
    """Creates a 'Bridge String' — abstract 1-sentence description."""
    try:
        prompt = f"""
        Analyze this joke: "{joke_text}"

        Write a 1-sentence "Search Description" for this joke.
        
        RULES:
        1. Do NOT mention specific nouns (e.g., don't say 'Coma', say 'Long Delay').
        2. Focus on the EMOTION and the MECHANISM.
        3. Use keywords that describe what kind of topics this joke fits.
        
        Example Output: "A joke about extreme procrastination where a high-stakes timeline is ignored for comfort."
        
        OUTPUT: Just the description, nothing else.
        """
        
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200
        )
        return response.choices[0].message.content.strip().strip('"').strip("'")
    except Exception as e:
        st.error(f"Bridge generation failed: {e}")
        return None

def expand_headline_to_themes(headline):
    """Expands a headline into abstract themes."""
    try:
        prompt = f"""
        Topic: "{headline}"
        
        List 5 abstract themes or concepts associated with this topic.
        
        Example: If topic is 'Traffic', themes are 'Waiting', 'Frustration', 'Wasting Time', 'Trapped'.
        
        OUTPUT: Just the comma-separated themes, nothing else.
        """
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=100
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        st.error(f"Theme expansion failed: {e}")
        return headline

def enrich_joke(joke_text):
    """Generate bridge + embedding. Returns dict."""
    result = {}
    bridge = create_joke_bridge(joke_text)
    if bridge:
        result['bridge_content'] = bridge
        embed = get_embedding(bridge)
        if embed:
            result['bridge_embedding'] = embed
    return result

# ─── V12 Generation ──────────────────────────────────────────────────────────

V12_SYSTEM_PROMPT = """You are a Comedy Architect. You reverse-engineer the logic of a reference joke and transplant it into a new topic.

YOUR PROCESS:
1. Analyze the 'Reference Joke' to find the Engine (A, B, or C).
2. BRAINSTORM 3 distinct mapping angles for the New Topic.
3. Select the funniest angle.
4. Draft the final joke.

---
THE ENGINES:

TYPE A: The "Word Trap" (Semantic/Pun)
- Logic: A trigger word bridges two unrelated contexts.
- Mapping: Find a word in the New Topic that has a double meaning. If none exists, FAIL and switch to Type C.

TYPE B: The "Behavior Trap" (Scenario/Character)
- Logic: Character applies a [Mundane Habit] to a [High-Stakes Situation], trivializing it.
- Mapping: 
  1. Identify the Abstract Behavior (e.g. "Being Cheap", "Being Lazy").
  2. You may SWAP the specific trait if a better one exists for the New Topic.
  3. Apply the Trait to the New Context. DO NOT PUN.

TYPE C: The "Hyperbole Engine" (Roast/Exaggeration)
- Logic: A physical trait is exaggerated until it breaks physics/social norms.
- Mapping: 
  1. Identify the Scale (e.g. Size, Weight, Wealth).
  2. Constraint: Conservation of Failure.
  3. Format: Statement ("He is so X..."), NOT a scene.

---
OUTPUT FORMAT (JSON ONLY):
{
  "engine_selected": "Type A/B/C",
  "reasoning": "Explain why this engine fits.",
  "brainstorming": [
    "Option 1: [Trait/Angle] -> [Scenario]",
    "Option 2: [Trait/Angle] -> [Scenario]",
    "Option 3: [Trait/Angle] -> [Scenario]"
  ],
  "selected_strategy": "The best option from above",
  "draft_joke": "The final joke text. Max 40 words. NO FILLER. Start directly with the setup."
}"""

def generate_v12_joke(reference_joke, new_topic):
    if not gemini_client:
        return {"success": False, "error": "Gemini API not configured"}
    
    from google.genai import types
    prompt = f"""REFERENCE JOKE:
"{reference_joke}"

NEW TOPIC:
"{new_topic}"

Analyze the reference joke, brainstorm 3 mapping angles, select the funniest, and draft the final joke."""

    try:
        config = types.GenerateContentConfig(
            temperature=0.7, # Slightly higher for creativity
            max_output_tokens=8192,
            system_instruction=V12_SYSTEM_PROMPT,
            response_mime_type="application/json"
        )
        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=config
        )
        return json.loads(response.text)
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── UI Layout ───────────────────────────────────────────────────────────────

st.title("🎭 Joke Manager")

tab_gen, tab_search, tab_db, tab_add_video, tab_manual = st.tabs([
    "🎬 Generate", "🔍 Search", "📊 DB Explorer", "➕ Add Video", "✍️ Add Joke"
])

# ─── TAB: GENERATE ───────────────────────────────────────────────────────────
with tab_gen:
    st.header("🎬 Campaign Generator (V12)")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        headline = st.text_area("New Headline / Topic", height=100, placeholder="e.g. Bangalore traffic is so bad...")
    with col2:
        count = st.number_input("Count", min_value=1, max_value=30, value=5)
        st.write("")
        st.write("")
        gen_btn = st.button("🚀 Generate", type="primary")

    if gen_btn and headline:
        if not gemini_client:
            st.error("Gemini API not configured.")
        else:
            with st.status("generating campaign...", expanded=True) as status:
                st.write("🔍 Expanding themes...")
                themes = expand_headline_to_themes(headline)
                st.write(f"Themes: `{themes}`")
                
                st.write("🔎 Searching bridges...")
                theme_embed = get_embedding(themes)
                
                # Search bridges
                try:
                    matches = supabase.rpc(
                        'match_joke_bridges',
                        {'query_embedding': theme_embed, 'match_count': count * 2}
                    ).execute()
                    candidates = matches.data[:count]
                except Exception as e:
                    st.error(f"DB Error: {e}")
                    candidates = []

                if not candidates:
                    status.update(label="No matches found", state="error")
                else:
                    st.write(f"✅ Found {len(candidates)} bridge matches")
                    
                    results = []
                    progress_bar = st.progress(0)
                    
                    for i, cand in enumerate(candidates):
                        status.update(label=f"Generating joke {i+1}/{len(candidates)}...")
                        ref_joke = cand.get('searchable_text', '')
                        
                        gen_res = generate_v12_joke(ref_joke, headline)
                        
                        if gen_res and "draft_joke" in gen_res:
                            results.append({
                                "reference": ref_joke,
                                "bridge": cand.get('bridge_content', 'N/A'),
                                "generated": gen_res
                            })
                        progress_bar.progress((i + 1) / len(candidates))
                    
                    status.update(label="Campaign Complete!", state="complete")
                    
                    st.divider()
                    for res in results:
                        gen = res['generated']
                        with st.container(border=True):
                            col_a, col_b = st.columns([3, 1])
                            with col_a:
                                st.subheader(gen.get("draft_joke", "Failed"))
                                st.caption(f"Strategy: {gen.get('selected_strategy')}")
                                with st.expander("Brainstorming & Reference"):
                                    st.write("**Reference Joke:**", res['reference'])
                                    st.write("**Bridge:**", res['bridge'])
                                    st.write("**Brainstorming:**")
                                    for opt in gen.get('brainstorming', []):
                                        st.write(f"- {opt}")
                            with col_b:
                                st.metric("Engine", gen.get("engine_selected", "?"))

# ─── TAB: SEARCH ─────────────────────────────────────────────────────────────
with tab_search:
    st.header("🔍 Semantic Search")
    query = st.text_input("Search query", placeholder="Find jokes about...")
    
    if query:
        with st.spinner("Searching..."):
            emb = get_embedding(query)
            try:
                res = supabase.rpc(
                    'match_joke_bridges',
                    {'query_embedding': emb, 'match_count': 10}
                ).execute()
                
                for item in res.data:
                    with st.container(border=True):
                        st.markdown(f"**{item['searchable_text']}**")
                        st.caption(f"Bridge: {item.get('bridge_content')}")
                        st.caption(f"Similarity: {item['similarity']:.3f} | ID: {item['id']}")
            except Exception as e:
                st.error(f"Search error: {e}")

# ─── TAB: DB EXPLORER ────────────────────────────────────────────────────────
# ─── TAB: DB EXPLORER ────────────────────────────────────────────────────────
with tab_db:
    st.header("📊 Database Explorer")
    
    # Stats
    try:
        count_res = supabase.table("comic_segments").select("id", count="exact").execute()
        bridge_res = supabase.table("comic_segments").select("id", count="exact").is_("bridge_content", "null").execute()
        total = count_res.count
        missing = bridge_res.count
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Jokes", total)
        c2.metric("Missing Bridges", missing)
        c3.metric("Indexed", total - missing)
    except Exception as e:
        st.error(f"Stats error: {e}")

    st.divider()
    
    # Search within DB
    db_search = st.text_input("Filter by text", placeholder="Type to filter...")
    
    # Table View
    limit = st.select_slider("Rows to load", options=[10, 50, 100, 500], value=50)
    
    try:
        query = supabase.table("comic_segments").select("*").order("created_at", desc=True).limit(limit)
        if db_search:
            query = query.ilike("searchable_text", f"%{db_search}%")
            
        data = query.execute()
        
        if not data.data:
            st.info("No jokes found.")
        else:
            for item in data.data:
                with st.container(border=True):
                    c1, c2 = st.columns([5, 1])
                    with c1:
                        st.markdown(f"**{item['searchable_text']}**")
                        st.caption(f"ID: {item['id']} | Video: {item['video_id']}")
                        if item.get('bridge_content'):
                            with st.expander("Bridge"):
                                st.write(item['bridge_content'])
                        else:
                            st.caption("⚠️ No bridge")
                            if st.button("Generate Bridge", key=f"bridge_{item['id']}"):
                                with st.spinner("Generating..."):
                                    enrich = enrich_joke(item['searchable_text'])
                                    if enrich:
                                        supabase.table("comic_segments").update(enrich).eq("id", item['id']).execute()
                                        st.rerun()

                    with c2:
                        # EDIT
                        with st.popover("✏️ Edit"):
                            new_text = st.text_area("Edit Text", value=item['searchable_text'], key=f"edit_text_{item['id']}")
                            if st.button("Save", key=f"save_{item['id']}"):
                                supabase.table("comic_segments").update({"searchable_text": new_text}).eq("id", item['id']).execute()
                                st.success("Saved!")
                                time.sleep(1)
                                st.rerun()
                        
                        # DELETE
                        if st.button("🗑️", key=f"del_{item['id']}", help="Delete Joke"):
                            if st.session_state.get(f"confirm_{item['id']}"):
                                supabase.table("comic_segments").delete().eq("id", item['id']).execute()
                                st.success("Deleted!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.session_state[f"confirm_{item['id']}"] = True
                                st.warning("Click again to confirm delete")
                                
    except Exception as e:
        st.error(f"Load error: {e}")

# ─── TAB: ADD VIDEO ──────────────────────────────────────────────────────────
with tab_add_video:
    st.header("➕ Add from YouTube")
    
    # Initialize session state for extracted jokes
    if 'extracted_jokes' not in st.session_state:
        st.session_state.extracted_jokes = []
    if 'video_id' not in st.session_state:
        st.session_state.video_id = None
    
    url = st.text_input("YouTube URL", key="yt_url")
    lang = st.selectbox("Language", ["english", "hindi", "hinglish"], key="yt_lang")
    
    col_process, col_clear = st.columns([3, 1])
    with col_process:
        process_btn = st.button("🔍 Process Video", type="primary")
    with col_clear:
        if st.button("🗑️ Clear Results"):
            st.session_state.extracted_jokes = []
            st.session_state.video_id = None
            st.rerun()
    
    # ── Step 1: Process Video & Extract Jokes ───────────────────
    if process_btn and url:
        with st.status("Processing transcript...", expanded=True) as status:
            video_id_match = re.search(r"(?:v=|/)([0-9A-Za-z_-]{11})", url)
            if not video_id_match:
                st.error("Invalid YouTube URL")
                st.stop()
            vid = video_id_match.group(1)
            
            try:
                # Fetch transcript (v1.x API)
                st.write("📡 Fetching transcript...")
                ytt_api = YouTubeTranscriptApi()
                transcript_data = ytt_api.fetch(vid)
                full_text = " ".join([snippet.text for snippet in transcript_data])
                st.write(f"✅ Fetched {len(full_text)} chars.")
                
                # Chunk with overlap for better extraction
                chunk_size = 6000
                overlap = 1500
                chunks = []
                pos = 0
                while pos < len(full_text):
                    end_pos = min(pos + chunk_size, len(full_text))
                    chunks.append(full_text[pos:end_pos])
                    pos = end_pos - overlap if end_pos < len(full_text) else len(full_text)
                
                all_jokes = []
                bar = st.progress(0)
                for i, chunk in enumerate(chunks):
                    status.update(label=f"Extracting jokes from chunk {i+1}/{len(chunks)}...")
                    
                    sys_prompt = """You are a Comedy Curator. Extract ALL standout comedy segments from this transcript.
Return JSON: {"segments": [{"searchable_content": "the joke text cleaned up for readability", "keywords": ["tag1", "tag2"]}]}
IMPORTANT: Extract EVERY joke, don't skip any. Clean up the text for readability but keep the joke intact."""
                    
                    try:
                        resp = openai_client.chat.completions.create(
                            model="gpt-4o",
                            messages=[
                                {"role": "system", "content": sys_prompt},
                                {"role": "user", "content": f"Extract ALL jokes:\n{chunk}"}
                            ],
                            response_format={"type": "json_object"},
                            temperature=0.4
                        )
                        data = json.loads(resp.choices[0].message.content)
                        for seg in data.get('segments', []):
                            seg['selected'] = True
                            all_jokes.append(seg)
                    except Exception as chunk_err:
                        st.warning(f"Chunk {i+1} failed: {chunk_err}")
                    bar.progress((i + 1) / len(chunks))
                
                # Deduplicate
                unique = []
                seen = set()
                for j in all_jokes:
                    key = j.get('searchable_content', '')[:80].lower().strip()
                    if key and key not in seen:
                        seen.add(key)
                        unique.append(j)
                
                st.session_state.extracted_jokes = unique
                st.session_state.video_id = vid
                status.update(label=f"Done! Found {len(unique)} unique jokes.", state="complete")
                st.rerun()
                
            except Exception as e:
                st.error(f"Error: {e}")
    
    # ── Step 2: Review, Edit, Select & Push ──────────────────────
    if st.session_state.extracted_jokes:
        jokes = st.session_state.extracted_jokes
        vid = st.session_state.video_id
        
        st.success(f"📋 {len(jokes)} jokes extracted from video `{vid}` — Review, edit, and push below.")
        st.divider()
        
        # Select All / Deselect All
        col_sel, col_desel, col_push_all = st.columns(3)
        with col_sel:
            if st.button("☑️ Select All"):
                for j in st.session_state.extracted_jokes:
                    j['selected'] = True
                st.rerun()
        with col_desel:
            if st.button("⬜ Deselect All"):
                for j in st.session_state.extracted_jokes:
                    j['selected'] = False
                st.rerun()
        with col_push_all:
            push_all_btn = st.button("🚀 Push All Selected", type="primary")
        
        # Handle batch push
        if push_all_btn:
            selected = [j for j in jokes if j.get('selected', False)]
            if not selected:
                st.warning("No jokes selected!")
            else:
                rows = []
                progress = st.progress(0, text="Enriching & saving...")
                for idx, joke in enumerate(selected):
                    text = joke.get('searchable_content', '')
                    if text:
                        enrichment = enrich_joke(text)
                        db_row = {
                            "video_id": vid,
                            "searchable_text": text,
                            "meta_tags": joke.get('keywords', []),
                            "embedding": get_embedding(text)
                        }
                        db_row.update(enrichment)
                        rows.append(db_row)
                    progress.progress((idx + 1) / len(selected), text=f"Processing {idx+1}/{len(selected)}...")
                
                if rows:
                    supabase.table("comic_segments").insert(rows).execute()
                    st.success(f"✅ Saved {len(rows)} jokes to Supabase!")
                    # Remove pushed jokes from list
                    st.session_state.extracted_jokes = [j for j in jokes if not j.get('selected', False)]
                    time.sleep(1.5)
                    st.rerun()
        
        st.divider()
        
        # Individual joke cards
        for i, joke in enumerate(jokes):
            with st.container(border=True):
                col_check, col_text, col_actions = st.columns([0.5, 5, 1.5])
                
                with col_check:
                    selected = st.checkbox(
                        "Select", value=joke.get('selected', True), 
                        key=f"sel_{i}", label_visibility="collapsed"
                    )
                    st.session_state.extracted_jokes[i]['selected'] = selected
                
                with col_text:
                    # Editable joke text
                    new_text = st.text_area(
                        f"Joke #{i+1}", 
                        value=joke.get('searchable_content', ''), 
                        key=f"joke_text_{i}",
                        height=80,
                        label_visibility="collapsed"
                    )
                    st.session_state.extracted_jokes[i]['searchable_content'] = new_text
                    
                    # Tags
                    tags = joke.get('keywords', [])
                    if tags:
                        st.caption(f"🏷️ {', '.join(tags)}")
                
                with col_actions:
                    # Push individual joke
                    if st.button("📤 Push", key=f"push_{i}"):
                        text = new_text.strip()
                        if text:
                            with st.spinner("Saving..."):
                                enrichment = enrich_joke(text)
                                db_row = {
                                    "video_id": vid,
                                    "searchable_text": text,
                                    "meta_tags": joke.get('keywords', []),
                                    "embedding": get_embedding(text)
                                }
                                db_row.update(enrichment)
                                supabase.table("comic_segments").insert(db_row).execute()
                                st.success("✅ Saved!")
                                # Remove from list
                                st.session_state.extracted_jokes.pop(i)
                                time.sleep(1)
                                st.rerun()
                    
                    # Delete from review list
                    if st.button("❌", key=f"remove_{i}", help="Remove from list"):
                        st.session_state.extracted_jokes.pop(i)
                        st.rerun()

# ─── TAB: MANUAL ADD ─────────────────────────────────────────────────────────
with tab_manual:
    st.header("✍️ Manual Entry")
    with st.form("manual_add"):
        joke_text = st.text_area("Joke Text")
        tags = st.text_input("Tags (comma separated)")
        submitted = st.form_submit_button("Add Joke")
        
        if submitted and joke_text:
            with st.spinner("Enriching & Saving..."):
                enrichment = enrich_joke(joke_text)
                row = {
                    "video_id": "manual",
                    "searchable_text": joke_text,
                    "meta_tags": [t.strip() for t in tags.split(",") if t.strip()],
                    "embedding": get_embedding(joke_text)
                }
                row.update(enrichment)
                
                try:
                    supabase.table("comic_segments").insert(row).execute()
                    st.success("Joke added successfully!")
                    st.json(enrichment)
                except Exception as e:
                    st.error(f"Error: {e}")
