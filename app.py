import streamlit as st
from streamlit_mic_recorder import mic_recorder
import speech_recognition as sr
from groq import Groq
from gtts import gTTS
import io, json, os, subprocess
import imageio_ffmpeg as ffmpeg
import urllib.parse

# --- 1. AUDIO PROCESSING ---
def convert_audio_to_wav(webm_bytes):
    try:
        ffmpeg_exe = ffmpeg.get_ffmpeg_exe()
        process = subprocess.Popen(
            [ffmpeg_exe, "-i", "pipe:0", "-f", "wav", "pipe:1"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate(input=webm_bytes)
        return stdout
    except: return None

def speak(text):
    try:
        tts = gTTS(text=text, lang='en')
        audio_fp = io.BytesIO()
        tts.write_to_fp(audio_fp)
        audio_fp.seek(0)
        return audio_fp
    except: return None

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

# --- 3. CONFIG ---
st.set_page_config(page_title="Expert AI Secretary", layout="centered")

if "GROQ_API_KEY" in st.secrets:
    api_key = st.secrets["GROQ_API_KEY"]
else:
    api_key = "PASTE_YOUR_LOCAL_KEY_HERE"

client = Groq(api_key=api_key)
query_params = st.query_params
biz_id = query_params.get("biz")

if not biz_id:
    st.title("🔧 Admin: AI Setup")
    with st.form("registration"):
        biz_name = st.text_input("Business Name")
        biz_phone = st.text_input("WhatsApp Number (+91...)")
        if st.form_submit_button("Generate Link"):
            if biz_name and biz_phone.startswith("+"):
                bid = biz_name.replace(" ", "_").lower()
                save_to_db(bid, {"name": biz_name, "phone": biz_phone})
                st.success("Registration Successful!")
                st.code(f"https://6x4owrkmjbyhem4oftfsuc.streamlit.app/?biz={bid}")
else:
    data = get_db().get(biz_id)
    if data:
        st.title(f"{data['name']} 📞 Secretary")
        
        if "messages" not in st.session_state: st.session_state.messages = []
        if "last_id" not in st.session_state: st.session_state.last_id = None
        if "show_whatsapp" not in st.session_state: st.session_state.show_whatsapp = False

        if st.sidebar.button("New Call"):
            st.session_state.messages = []
            st.session_state.show_whatsapp = False
            st.rerun()

        # Display Chat
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])

        # WHATSAPP BUTTON (Stays visible once triggered)
        if st.session_state.show_whatsapp:
            transcript = ""
            for m in st.session_state.messages:
                role = "Customer" if m["role"] == "user" else "AI"
                transcript += f"*{role}:* {m['content'].replace('[DONE]', '').strip()}\n"
            
            full_lead_msg = f"🚨 *NEW LEAD* 🚨\n\n{transcript}"
            encoded_msg = urllib.parse.quote(full_lead_msg.replace('\xa0', ' '))
            whatsapp_url = f"https://wa.me/{data['phone']}?text={encoded_msg}"
            
            st.markdown(f"""
                <a href="{whatsapp_url}" target="_blank">
                    <button style="width:100%; background-color:#25D366; color:white; border:none; padding:15px; border-radius:10px; font-weight:bold; cursor:pointer; font-size:18px; margin-bottom:20px;">
                        ✅ Send Lead to WhatsApp
                    </button>
                </a>
            """, unsafe_allow_html=True)

        audio = mic_recorder(start_prompt="🎤 Tap to Speak", stop_prompt="🛑 Stop & Send", key='recorder')

        if audio and audio.get('id') != st.session_state.last_id:
            st.session_state.last_id = audio.get('id')
            with st.spinner("Mike is thinking..."):
                wav = convert_audio_to_wav(audio['bytes'])
                r = sr.Recognizer()
                try:
                    with sr.AudioFile(io.BytesIO(wav)) as source:
                        user_text = r.recognize_google(r.record(source))
                except: user_text = "[Audio Input]"
                
                st.session_state.messages.append({"role": "user", "content": user_text})
                
                system_prompt = f"You are Mike from {data['name']}. Get Name, Phone, Address, and Time. When finished, end your summary with [DONE]."
                messages = [{"role": "system", "content": system_prompt}] + st.session_state.messages
                ai_response = client.chat.completions.create(messages=messages, model="llama-3.1-8b-instant").choices[0].message.content
                
                st.session_state.messages.append({"role": "assistant", "content": ai_response})
                
                # Logic to trigger button
                if "[DONE]" in ai_response.replace(" ", "").upper():
                    st.session_state.show_whatsapp = True
                
                st.rerun()
    else:
        st.error("Business ID not found.")
