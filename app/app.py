"""
Joke Manager — V12-Aligned Management + Generation App

Features:
- DB Explorer: View all DB columns, refresh bridges
- Search jokes (semantic via bridge embeddings)
- Add joke manually (auto-generates bridge + embedding)
- Add jokes from YouTube videos (auto-generates bridge + embedding)
- Manage (edit/delete) jokes
- Generate: V12-style campaign generation (bridge search → Gemini classify + brainstorm + draft)

Port: 5025
"""
import os
import re
import json
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

# Configuration
APP_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.join(APP_DIR, "..")
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
load_dotenv(os.path.join(CONFIG_DIR, "credentials.env"))

# Load OpenAI key
OPENAI_KEY_FILE = os.path.join(CONFIG_DIR, "open_ai_api.txt")
with open(OPENAI_KEY_FILE, 'r') as f:
    OPENAI_KEY = f.read().strip().rstrip('.')

# Load Gemini API key for V12-style generation
GEMINI_KEY_FILE = os.path.join(APP_DIR, "..", "..", "geminiapi_key.env")
GEMINI_KEY = None
if os.path.exists(GEMINI_KEY_FILE):
    with open(GEMINI_KEY_FILE, 'r') as f:
        GEMINI_KEY = f.read().strip()

# Initialize clients
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

openai_client = OpenAI(api_key=OPENAI_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Gemini client (V12 generation)
gemini_client = None
if GEMINI_KEY:
    try:
        from google import genai
        gemini_client = genai.Client(api_key=GEMINI_KEY)
        print("✅ Gemini API connected")
    except ImportError:
        print("⚠️ google-genai not installed. Run: pip install google-genai")
    except Exception as e:
        print(f"⚠️ Gemini init failed: {e}")

app = Flask(__name__)


# ============= HELPER FUNCTIONS =============

def get_embedding(text):
    """Generate embedding for text using OpenAI."""
    text = text.replace("\n", " ").strip()
    if not text:
        return None
    response = openai_client.embeddings.create(
        input=[text],
        model="text-embedding-3-small"
    )
    return response.data[0].embedding


def create_joke_bridge(joke_text):
    """
    Creates a 'Bridge String' — abstract 1-sentence description of the joke's logic.
    This is V12's core search mechanism.
    """
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
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=200
        )
        
        bridge_string = response.choices[0].message.content.strip()
        bridge_string = bridge_string.strip('"').strip("'")
        
        return bridge_string
    except Exception as e:
        print(f"⚠️ Bridge generation failed: {e}")
        return None


def expand_headline_to_themes(headline):
    """
    V12: Expands a headline into abstract themes for semantic search.
    """
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
        print(f"⚠️ Theme expansion failed: {e}")
        return headline


def enrich_joke(joke_text):
    """Generate bridge content + embedding for a joke. Returns dict of fields to insert/update."""
    result = {}
    
    try:
        bridge_content = create_joke_bridge(joke_text)
        if bridge_content:
            result['bridge_content'] = bridge_content
            bridge_embedding = get_embedding(bridge_content)
            if bridge_embedding:
                result['bridge_embedding'] = bridge_embedding
    except Exception as e:
        print(f"⚠️ Bridge enrichment failed: {e}")
    
    return result


def extract_video_id(url):
    """Extract YouTube video ID from URL."""
    match = re.search(r"(?:v=|/)([0-9A-Za-z_-]{11})", url)
    return match.group(1) if match else None

def get_prompt_for_language(language):
    """Return appropriate prompt based on language."""
    if language in ['hindi', 'hinglish']:
        return """You are an expert Comedy Curator and Translator.
Extract "Standout Comedy Segments" from this Hindi/Hinglish transcript.

RULES:
1. NO SUMMARIES - TRANSLATE the actual funny monologue
2. Include 2-3 sentences of context (setup + punchline together)
3. Translation: "चीप" → "Cheap", keep it conversational
4. Ignore filler like "Thank you", [Music]
5. Preserve the exact comedy

OUTPUT JSON:
{"segments": [{"segment_id": 1, "original_text": "Hindi text", "searchable_content": "Full English/Hinglish translation", "keywords": ["tag1", "tag2"]}]}"""
    else:
        return """You are an expert Comedy Curator.
Extract "Standout Comedy Segments" from this English transcript.

RULES:
1. NO SUMMARIES - capture actual funny monologue
2. Include 2-3 sentences of context (setup + punchline together)  
3. Clean up [Applause], fix broken sentences
4. Ignore filler like "Thank you", [Music]
5. Preserve the exact comedy

OUTPUT JSON:
{"segments": [{"segment_id": 1, "original_text": "Exact text", "searchable_content": "Cleaned full segment", "keywords": ["tag1", "tag2"]}]}"""


# ============= V12 GENERATION ENGINE =============

GEMINI_MODEL = "gemini-2.0-flash"

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
  1. Identify the Abstract Behavior (e.g. "Being Cheap", "Being Lazy", "Professional Deformation").
  2. You may SWAP the specific trait if a better one exists for the New Topic. 
     (Example: If Ref is "Snoozing", you can swap to "Haggling" if the New Topic is "Medical Costs").
  3. Apply the Trait to the New Context. DO NOT PUN.

TYPE C: The "Hyperbole Engine" (Roast/Exaggeration)
- Logic: A physical trait is exaggerated until it breaks physics/social norms.
- Mapping: 
  1. Identify the Scale (e.g. Size, Weight, Wealth).
  2. Constraint: Conservation of Failure. If Ref fails due to "Lack of Substance," New Joke must also fail due to "Lack of Substance."
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
  "draft_joke": "The final joke text. Max 40 words. NO FILLER (e.g. 'The health crisis is dire'). Start directly with the setup."
}"""


def generate_v12_joke(reference_joke, new_topic):
    """
    V12 Generation: Pass raw joke text to Gemini, which classifies type,
    brainstorms 3 angles, selects best, and drafts a new joke.
    No pre-extracted structure needed.
    """
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
            temperature=0.5,
            max_output_tokens=8192,
            system_instruction=V12_SYSTEM_PROMPT,
            response_mime_type="application/json"
        )
        
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=config
        )
        
        result_text = response.text
        
        try:
            result = json.loads(result_text)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                result = json.loads(json_match.group())
            else:
                return {"success": False, "error": "Failed to parse Gemini response", "raw": result_text[:300]}
        
        result["success"] = True
        return result
        
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============= ROUTES =============

@app.route('/')
def index():
    return render_template('index.html')

# ---------- SEARCH ----------
@app.route('/api/search', methods=['POST'])
def search():
    """Search for jokes using bridge embedding similarity (V12-style)."""
    data = request.json
    query = data.get('query', '').strip()
    
    if not query:
        return jsonify({'error': 'No query provided'}), 400
    
    try:
        # Expand to themes first, then embed
        themes = expand_headline_to_themes(query)
        query_embedding = get_embedding(themes)
        
        # Use bridge search (V12's match_joke_bridges)
        try:
            result = supabase.rpc(
                'match_joke_bridges',
                {
                    'query_embedding': query_embedding,
                    'match_count': 15
                }
            ).execute()
        except Exception:
            # Fallback to regular match_jokes if bridge RPC not available
            result = supabase.rpc(
                'match_jokes',
                {
                    'query_embedding': query_embedding,
                    'match_threshold': 0.15,
                    'match_count': 15
                }
            ).execute()
        
        return jsonify({
            'success': True,
            'themes': themes,
            'results': result.data,
            'count': len(result.data)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------- MANAGE SEGMENTS ----------
@app.route('/api/segments', methods=['GET'])
def get_all_segments():
    """Get all segments for management — includes bridge info."""
    try:
        result = supabase.table("comic_segments") \
            .select("id, video_id, original_text, searchable_text, meta_tags, bridge_content, created_at") \
            .order("created_at", desc=True) \
            .execute()
        
        # Check bridge_embedding existence separately (it's a big vector, don't return it)
        embed_check = supabase.table("comic_segments") \
            .select("id, bridge_embedding") \
            .order("created_at", desc=True) \
            .execute()
        
        embed_map = {}
        for row in embed_check.data:
            embed_map[row['id']] = row.get('bridge_embedding') is not None
        
        for seg in result.data:
            seg['has_bridge_embedding'] = embed_map.get(seg['id'], False)
        
        return jsonify({'success': True, 'segments': result.data})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/segments/<int:segment_id>', methods=['PUT'])
def update_segment(segment_id):
    """Update a segment."""
    data = request.json
    try:
        searchable = data.get('searchable_text', '')
        embedding = get_embedding(searchable) if searchable else None
        
        update_data = {
            'original_text': data.get('original_text', ''),
            'searchable_text': searchable,
            'meta_tags': data.get('meta_tags', [])
        }
        
        if embedding:
            update_data['embedding'] = embedding
        
        supabase.table("comic_segments").update(update_data).eq("id", segment_id).execute()
        return jsonify({'success': True, 'message': 'Segment updated!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/segments/<int:segment_id>', methods=['DELETE'])
def delete_segment(segment_id):
    """Delete a segment."""
    try:
        supabase.table("comic_segments").delete().eq("id", segment_id).execute()
        return jsonify({'success': True, 'message': 'Segment deleted!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------- SEGMENT DETAILS ----------
@app.route('/api/segments/<int:segment_id>/details', methods=['GET'])
def get_segment_details(segment_id):
    """Get ALL DB columns for a single joke."""
    try:
        result = supabase.table("comic_segments") \
            .select("id, video_id, original_text, searchable_text, meta_tags, structure, tone, bridge_content, created_at") \
            .eq("id", segment_id) \
            .execute()
        
        if not result.data:
            return jsonify({'error': 'Segment not found'}), 404
        
        seg = result.data[0]
        
        # Check embedding existence
        embed_check = supabase.table("comic_segments") \
            .select("id, bridge_embedding, embedding") \
            .eq("id", segment_id) \
            .execute()
        
        if embed_check.data:
            seg['has_bridge_embedding'] = embed_check.data[0].get('bridge_embedding') is not None
            seg['has_embedding'] = embed_check.data[0].get('embedding') is not None
        
        return jsonify({'success': True, 'segment': seg})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------- REFRESH BRIDGE ----------
@app.route('/api/segments/<int:segment_id>/refresh-bridge', methods=['POST'])
def refresh_bridge(segment_id):
    """Re-run bridge generation for a specific joke, overwriting existing."""
    try:
        result = supabase.table("comic_segments") \
            .select("id, searchable_text") \
            .eq("id", segment_id) \
            .execute()
        
        if not result.data:
            return jsonify({'error': 'Segment not found'}), 404
        
        joke_text = result.data[0]['searchable_text']
        
        # Generate bridge
        bridge_content = create_joke_bridge(joke_text)
        
        if not bridge_content:
            return jsonify({'error': 'Failed to generate bridge content'}), 500
        
        # Generate embedding for the bridge
        bridge_embedding = get_embedding(bridge_content)
        
        update_data = {'bridge_content': bridge_content}
        if bridge_embedding:
            update_data['bridge_embedding'] = bridge_embedding
        
        supabase.table("comic_segments").update(update_data).eq("id", segment_id).execute()
        
        return jsonify({
            'success': True,
            'segment_id': segment_id,
            'bridge_content': bridge_content,
            'has_bridge_embedding': bridge_embedding is not None,
            'message': 'Bridge refreshed successfully!'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------- ADD VIDEO ----------
@app.route('/api/process-video', methods=['POST'])
def process_video():
    """Process a YouTube video and return segments for review."""
    data = request.json
    url = data.get('url', '').strip()
    language = data.get('language', 'english')
    
    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({'error': 'Invalid YouTube URL'}), 400
    
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        
        transcript = None
        for lang in ['hi', 'en', 'en-IN']:
            try:
                transcript = transcript_list.find_transcript([lang])
                break
            except:
                continue
        
        if not transcript:
            transcript = list(transcript_list)[0]
        
        transcript_data = transcript.fetch()
        formatter = TextFormatter()
        raw_text = formatter.format_transcript(transcript_data)
        
        print(f"\n📝 Transcript Length: {len(raw_text)} characters")
        
        prompt = get_prompt_for_language(language)
        
        chunk_size = 6000
        overlap = 2000
        all_segments = []
        
        chunks = []
        pos = 0
        while pos < len(raw_text):
            end_pos = min(pos + chunk_size, len(raw_text))
            chunk = raw_text[pos:end_pos]
            chunks.append({
                'text': chunk,
                'start': pos,
                'end': end_pos
            })
            pos = end_pos - overlap if end_pos < len(raw_text) else len(raw_text)
        
        print(f"📦 Created {len(chunks)} chunks (with {overlap} char overlap)")
        
        for i, chunk_data in enumerate(chunks):
            chunk = chunk_data['text']
            print(f"\n🔄 Processing chunk {i+1}/{len(chunks)} (chars {chunk_data['start']}-{chunk_data['end']})")
            
            try:
                response = openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "Comedy curator. Output valid JSON only. Extract ALL comedy segments, don't skip any."},
                        {"role": "user", "content": f"{prompt}\n\nIMPORTANT: Extract ALL comedy segments from this transcript section. Do not skip any jokes.\n\nTRANSCRIPT:\n{chunk}"}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.4
                )
                
                result = json.loads(response.choices[0].message.content)
                segments = result.get('segments', [])
                
                print(f"   Found {len(segments)} segments in this chunk")
                
                for seg in segments:
                    seg['chunk_index'] = i
                    seg['selected'] = True
                    all_segments.append(seg)
                    
            except Exception as chunk_error:
                print(f"   ❌ Error processing chunk {i+1}: {chunk_error}")
                continue
        
        print(f"\n📊 Total raw segments: {len(all_segments)}")
        
        # Deduplication
        unique_segments = []
        seen_texts = set()
        
        for seg in all_segments:
            original = seg.get('original_text', '').strip().lower()
            searchable = seg.get('searchable_content', '').strip().lower()
            key = original[:100] if original else searchable[:100]
            
            if key and key not in seen_texts:
                seen_texts.add(key)
                seg['segment_id'] = len(unique_segments) + 1
                unique_segments.append(seg)
        
        print(f"📊 After deduplication: {len(unique_segments)} unique segments")
        
        return jsonify({
            'success': True,
            'video_id': video_id,
            'segments': unique_segments,
            'count': len(unique_segments),
            'transcript_length': len(raw_text),
            'chunks_processed': len(chunks)
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload-segments', methods=['POST'])
def upload_segments():
    """Upload reviewed segments to Supabase with auto bridge enrichment."""
    data = request.json
    video_id = data.get('video_id')
    segments = data.get('segments', [])
    
    if not video_id or not segments:
        return jsonify({'error': 'No video ID or segments provided'}), 400
    
    try:
        rows_to_insert = []
        
        for seg in segments:
            searchable = seg.get('searchable_content', '')
            if not searchable:
                continue
            
            embedding = get_embedding(searchable)
            if embedding:
                row_data = {
                    "video_id": video_id,
                    "original_text": seg.get('original_text', ''),
                    "searchable_text": searchable,
                    "embedding": embedding,
                    "meta_tags": seg.get('keywords', [])
                }
                
                # Auto-enrich: generate bridge + bridge embedding
                enrichment = enrich_joke(searchable)
                row_data.update(enrichment)
                
                rows_to_insert.append(row_data)
        
        if rows_to_insert:
            supabase.table("comic_segments").insert(rows_to_insert).execute()
        
        return jsonify({
            'success': True,
            'segments_added': len(rows_to_insert),
            'message': f'Added {len(rows_to_insert)} segments with bridge embeddings!'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------- MANUAL JOKE ADDITION ----------
@app.route('/api/add-joke', methods=['POST'])
def add_joke():
    """Manually add a joke — auto-generates embedding + bridge."""
    data = request.json
    joke_text = data.get('joke_text', '').strip()
    keywords = data.get('keywords', [])
    source = data.get('source', 'manual')
    
    if not joke_text:
        return jsonify({'error': 'No joke text provided'}), 400
    
    try:
        embedding = get_embedding(joke_text)
        
        if not embedding:
            return jsonify({'error': 'Could not generate embedding'}), 500
        
        row = {
            "video_id": source,
            "original_text": "",
            "searchable_text": joke_text,
            "embedding": embedding,
            "meta_tags": keywords if keywords else []
        }
        
        # Auto-enrich: generate bridge + bridge embedding
        enrichment = enrich_joke(joke_text)
        row.update(enrichment)
        
        supabase.table("comic_segments").insert(row).execute()
        
        return jsonify({
            'success': True,
            'has_bridge': 'bridge_content' in enrichment,
            'bridge_content': enrichment.get('bridge_content', ''),
            'message': 'Joke added with bridge embedding!'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------- STATS ----------
@app.route('/api/stats')
def stats():
    """Get database statistics."""
    try:
        result = supabase.table("comic_segments").select("video_id, bridge_content", count="exact").execute()
        
        videos = {}
        with_bridge = 0
        for row in result.data:
            vid = row['video_id']
            videos[vid] = videos.get(vid, 0) + 1
            if row.get('bridge_content'):
                with_bridge += 1
        
        return jsonify({
            'total_segments': result.count,
            'with_bridge': with_bridge,
            'without_bridge': result.count - with_bridge,
            'videos': videos
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------- FILL ALL MISSING BRIDGES ----------
@app.route('/api/fill-all-missing', methods=['POST'])
def fill_all_missing():
    """Batch-fill all missing bridges."""
    data = request.json or {}
    batch_size = data.get('batch_size', 10)
    
    try:
        all_jokes = supabase.table("comic_segments") \
            .select("id, searchable_text, bridge_content") \
            .is_("bridge_content", "null") \
            .order("id") \
            .limit(batch_size) \
            .execute()
        
        if not all_jokes.data:
            return jsonify({
                'success': True,
                'message': 'All jokes have bridges! Nothing to fill.',
                'processed': 0,
                'remaining': 0
            })
        
        processed = []
        errors = []
        
        for joke in all_jokes.data:
            joke_id = joke['id']
            joke_text = joke.get('searchable_text', '')
            
            if not joke_text:
                errors.append({'id': joke_id, 'error': 'No searchable text'})
                continue
            
            try:
                bridge_content = create_joke_bridge(joke_text)
                if bridge_content:
                    bridge_embedding = get_embedding(bridge_content)
                    update_data = {'bridge_content': bridge_content}
                    if bridge_embedding:
                        update_data['bridge_embedding'] = bridge_embedding
                    
                    supabase.table("comic_segments").update(update_data).eq("id", joke_id).execute()
                    processed.append({
                        'id': joke_id,
                        'bridge': bridge_content[:80]
                    })
                else:
                    errors.append({'id': joke_id, 'error': 'Bridge generation failed'})
                    
            except Exception as e:
                errors.append({'id': joke_id, 'error': str(e)})
        
        # Count remaining
        remaining_check = supabase.table("comic_segments") \
            .select("id", count="exact") \
            .is_("bridge_content", "null") \
            .execute()
        remaining = remaining_check.count or 0
        
        return jsonify({
            'success': True,
            'processed': len(processed),
            'errors': len(errors),
            'remaining': remaining,
            'results': processed,
            'error_details': errors if errors else None,
            'message': f'Filled {len(processed)} bridges. {remaining} still remaining.'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------- V12 CAMPAIGN GENERATION ----------
@app.route('/api/generate-campaign', methods=['POST'])
def generate_campaign():
    """
    V12-style generation: 
    1. Expand headline to themes
    2. Search bridge embeddings for similar jokes
    3. For each match, pass raw joke text to Gemini → classify + brainstorm + draft
    """
    data = request.json
    headline = data.get('headline', '').strip()
    count = data.get('count', 10)
    
    if not headline:
        return jsonify({'error': 'No headline provided'}), 400
    
    if not gemini_client:
        return jsonify({'error': 'Gemini API not configured. Check geminiapi_key.env'}), 500
    
    try:
        # 1. Expand headline to themes
        themes = expand_headline_to_themes(headline)
        print(f"\n🔍 Themes: {themes}")
        
        # 2. Embed and search bridge embeddings
        query_embedding = get_embedding(themes)
        
        try:
            matches = supabase.rpc(
                'match_joke_bridges',
                {
                    'query_embedding': query_embedding,
                    'match_count': count
                }
            ).execute()
        except Exception:
            matches = supabase.rpc(
                'match_jokes',
                {
                    'query_embedding': query_embedding,
                    'match_threshold': 0.10,
                    'match_count': count
                }
            ).execute()
        
        if not matches.data:
            return jsonify({
                'success': True,
                'headline': headline,
                'themes': themes,
                'total_generated': 0,
                'jokes': [],
                'message': 'No matching jokes found in database.'
            })
        
        # 3. For each match, generate via Gemini
        results = []
        for i, match in enumerate(matches.data):
            reference_joke = match.get('searchable_text', '')
            joke_id = match.get('id')
            similarity = match.get('similarity', 0)
            bridge = match.get('bridge_content', '')
            
            print(f"\n[{i+1}/{len(matches.data)}] Ref #{joke_id} (sim: {similarity:.3f})")
            
            try:
                generated = generate_v12_joke(reference_joke, headline)
                
                if generated.get('success'):
                    results.append({
                        'original_id': joke_id,
                        'reference_joke': reference_joke[:150] + '...' if len(reference_joke) > 150 else reference_joke,
                        'bridge_content': bridge,
                        'similarity': round(similarity, 3),
                        'engine': generated.get('engine_selected', ''),
                        'reasoning': generated.get('reasoning', ''),
                        'brainstorming': generated.get('brainstorming', []),
                        'selected_strategy': generated.get('selected_strategy', ''),
                        'joke': generated.get('draft_joke', ''),
                    })
                    print(f"   ✅ [{generated.get('engine_selected')}] {generated.get('draft_joke', '')[:80]}")
                else:
                    print(f"   ❌ {generated.get('error', 'Unknown error')}")
                    
            except Exception as e:
                print(f"   ❌ Error: {e}")
                continue
        
        return jsonify({
            'success': True,
            'headline': headline,
            'themes': themes,
            'total_generated': len(results),
            'jokes': results
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("""
╔═══════════════════════════════════════════════════════════╗
║              🎭 JOKE MANAGER (V12-Aligned)                ║
║                                                           ║
║  🌉 Bridge Embeddings (V12 Core)                          ║
║  🎬 V12 Campaign Generation (Gemini)                      ║
║  📊 DB Explorer                                           ║
║  ➕ Add Jokes / Videos                                     ║
║  ⚙️  Edit / Delete / Manage                                ║
║                                                           ║
║  Running on: http://localhost:5025                         ║
╚═══════════════════════════════════════════════════════════╝
    """)
    app.run(debug=True, port=5025)
