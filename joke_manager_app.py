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
from youtube_transcript_api.formatters import TextFormatter

# ─── Config & Setup ──────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Joke Manager",
    page_icon="🎭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 50%, #16213e 100%);
        color: #e0e0e0;
    }
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        height: 3em;
        font-weight: 600;
    }
    /* Cards */
    div.st-emotion-cache-1r6slb0, div.st-emotion-cache-1629p8f {
        background-color: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 1rem;
    }
    /* Success badges */
    .badge-success {
        background-color: rgba(39, 174, 96, 0.2);
        color: #2ecc71;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.8rem;
    }
    /* Warning badges */
    .badge-warning {
        background-color: rgba(243, 156, 18, 0.2);
        color: #f39c12;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.8rem;
    }
</style>
""", unsafe_allow_html=True)


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
    
    # Table View
    limit = st.select_slider("Rows to load", options=[10, 50, 100, 500], value=50)
    
    try:
        data = supabase.table("comic_segments").select("*").order("created_at", desc=True).limit(limit).execute()
        df = pd.DataFrame(data.data)
        if not df.empty:
            st.dataframe(
                df[["id", "searchable_text", "bridge_content", "created_at", "meta_tags"]],
                use_container_width=True,
                hide_index=True
            )
    except Exception as e:
        st.error(f"Load error: {e}")

# ─── TAB: ADD VIDEO ──────────────────────────────────────────────────────────
with tab_add_video:
    st.header("➕ Add from YouTube")
    url = st.text_input("YouTube URL")
    lang = st.selectbox("Language", ["english", "hindi", "hinglish"])
    
    if st.button("Process Video") and url:
        with st.status("Processing transcript...") as status:
            video_id_match = re.search(r"(?:v=|/)([0-9A-Za-z_-]{11})", url)
            if not video_id_match:
                st.error("Invalid URL")
                st.stop()
            video_id = video_id_match.group(1)
            
            try:
                # Fetch transcript
                t_list = YouTubeTranscriptApi.list_transcripts(video_id)
                transcript = None
                try:
                    transcript = t_list.find_transcript(['hi', 'en', 'en-IN'])
                except:
                    transcript = t_list.find_generated_transcript(['en'])
                
                parts = transcript.fetch()
                full_text = TextFormatter().format_transcript(parts)
                st.write(f"Fetched {len(full_text)} chars.")
                
                # Extract jokes (simplified for Streamlit)
                # For robustness, we'll process 1 chunk for now or loop
                chunk_size = 8000
                chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
                
                extracted_jokes = []
                
                bar = st.progress(0)
                for i, chunk in enumerate(chunks):
                    status.update(label=f"Extracting jokes from chunk {i+1}/{len(chunks)}...")
                    
                    sys_prompt = "You are a Comedy Curator. Extract 'Standout Comedy Segments'. Return JSON: {'segments': [{'searchable_content': 'joke text', 'keywords': ['tag']}]}"
                    
                    resp = openai_client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": f"Extract jokes:\n{chunk}"}
                        ],
                        response_format={"type": "json_object"}
                    )
                    data = json.loads(resp.choices[0].message.content)
                    extracted_jokes.extend(data.get('segments', []))
                    bar.progress((i + 1) / len(chunks))
                
                if extracted_jokes:
                    st.success(f"Found {len(extracted_jokes)} jokes!")
                    
                    # Review & Save
                    display_df = pd.DataFrame(extracted_jokes)
                    edited_df = st.data_editor(display_df, num_rows="dynamic")
                    
                    if st.button("Save Selected to DB"):
                        rows = []
                        with st.spinner("Saving & Enriching..."):
                            for _, row in edited_df.iterrows():
                                text = row.get('searchable_content')
                                if text:
                                    enrichment = enrich_joke(text)
                                    db_row = {
                                        "video_id": video_id,
                                        "searchable_text": text,
                                        "meta_tags": row.get('keywords', []),
                                        "embedding": get_embedding(text)
                                    }
                                    db_row.update(enrichment)
                                    rows.append(db_row)
                            
                            if rows:
                                supabase.table("comic_segments").insert(rows).execute()
                                st.success(f"Saved {len(rows)} jokes!")
            except Exception as e:
                st.error(f"Error: {e}")

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
