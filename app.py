import streamlit as st
from streamlit_mic_recorder import mic_recorder
import speech_recognition as sr
from groq import Groq
from gtts import gTTS
import io, json, os, subprocess
import imageio_ffmpeg as ffmpeg
import urllib.parse

# --- 1. AUDIO ENGINE ---
def convert_audio_to_wav(webm_bytes):
    try:
        ffmpeg_exe = ffmpeg.get_ffmpeg_exe()
        process = subprocess.Popen(
            [ffmpeg_exe, "-i", "pipe:0", "-f", "wav", "pipe:1"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate(input=webm_bytes)
        return stdout
    except Exception as e:
        return None

def speak(text):
    tts = gTTS(text=text, lang='en')
    audio_fp = io.BytesIO()
    tts.write_to_fp(audio_fp)
    audio_fp.seek(0)
    return audio_fp

# --- 2. DATABASE ---
DB_FILE = "plumbers_db.json"
def get_db():
    if not os.path.exists(DB_FILE): return {}
    try:
        with open(DB_FILE, "r") as f: return json.load(f)
    except: return {}

def save_to_db(biz_id, data):
    db = get_db()
    db[biz_id] = data
    with open(DB_FILE, "w") as f: json.dump(db, f)

# --- 3. APP SETUP ---
st.set_page_config(page_title="Expert AI Secretary", layout="centered")

# SECRETS HANDLING: We will set this up in Step 5
if "GROQ_API_KEY" in st.secrets:
    api_key = st.secrets["GROQ_API_KEY"]
else:
    api_key = "PASTE_YOUR_KEY_HERE_FOR_LOCAL_TESTING"

client = Groq(api_key=api_key)

query_params = st.query_params
biz_id = query_params.get("biz")

if not biz_id:
    st.title("🔧 Admin: AI Setup")
    with st.form("registration"):
        biz_name = st.text_input("Business Name")
        biz_phone = st.text_input("WhatsApp Number (e.g., +91...)")
        if st.form_submit_button("Generate Link"):
            bid = biz_name.replace(" ", "_").lower()
            save_to_db(bid, {"name": biz_name, "phone": biz_phone})
            st.success("Registered!")
            st.code(f"https://YOUR-APP-NAME.streamlit.app/?biz={bid}")
else:
    data = get_db().get(biz_id)
    if data:
        st.title(f"{data['name']} 📞 Secretary")
        if "messages" not in st.session_state: st.session_state.messages = []
        if "last_id" not in st.session_state: st.session_state.last_id = None
        if "lead_sent" not in st.session_state: st.session_state.lead_sent = False

        if st.sidebar.button("Reset Session"):
            st.session_state.messages = []
            st.session_state.lead_sent = False
            st.rerun()

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])

        audio = mic_recorder(start_prompt="🎤 Tap to Speak", stop_prompt="🛑 Stop & Send", key='recorder')

        if audio and audio.get('id') != st.session_state.last_id:
            st.session_state.last_id = audio.get('id')
            with st.spinner("Processing..."):
                wav = convert_audio_to_wav(audio['bytes'])
                r = sr.Recognizer()
                with sr.AudioFile(io.BytesIO(wav)) as source:
                    audio_data = r.record(source)
                    user_text = r.recognize_google(audio_data)
                
                st.session_state.messages.append({"role": "user", "content": user_text})
                
                prompt = f"You are Mike, an expert plumber from {data['name']}. Diagnose the issue, build trust, and schedule. Get Name, Phone, Address, and Time. End with [DONE]."
                messages = [{"role": "system", "content": prompt}] + st.session_state.messages
                ai_response = client.chat.completions.create(messages=messages, model="llama-3.1-8b-instant").choices[0].message.content
                st.session_state.messages.append({"role": "assistant", "content": ai_response})
                
                st.audio(speak(ai_response.replace("[DONE]", "")), format="audio/mp3", autoplay=True)

                if "[DONE]" in ai_response and not st.session_state.lead_sent:
                    st.session_state.lead_sent = True
                    # Format message for WhatsApp
                    transcript = ""
                    for m in st.session_state.messages:
                        role = "Customer" if m["role"] == "user" else "AI"
                        transcript += f"*{role}:* {m['content'].replace('[DONE]', '').strip()}\n"
                    
                    full_msg = f"🚨 *NEW LEAD* 🚨\n\n{ai_response.replace('[DONE]','')}\n\n*Transcript:*\n{transcript}"
                    encoded_msg = urllib.parse.quote(full_msg)
                    whatsapp_url = f"https://wa.me/{data['phone']}?text={encoded_msg}"
                    
                    st.markdown(f"""
                        <a href="{whatsapp_url}" target="_blank">
                            <button style="width:100%; background-color:#25D366; color:white; border:none; padding:15px; border-radius:10px; font-weight:bold; cursor:pointer;">
                                ✅ Click to Send Lead to WhatsApp
                            </button>
                        </a>
                    """, unsafe_allow_html=True)
                st.rerun()