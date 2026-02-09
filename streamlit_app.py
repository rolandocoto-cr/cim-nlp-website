import requests
import streamlit as st
import threading
from streamlit_option_menu import option_menu

st.set_page_config(page_title="Cook Islands Māori NLP")

# ── Initialize TTS session state ─────────────────────────────────────────────
if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'audio_bytes' not in st.session_state:
    st.session_state.audio_bytes = None
if 'error_message' not in st.session_state:
    st.session_state.error_message = None
if 'user_text' not in st.session_state:
    st.session_state.user_text = "Kia orana kōtou kātoatoa"
if 'input_key' not in st.session_state:
    st.session_state.input_key = 0

# ── Top navigation menu ─────────────────────────────────────────────────────
page = option_menu(
    menu_title=None,
    options=["Home", "Transcription", "Voice Generation", "Parsing", "Spell Checking", "Forced Alignment", "About"],
    icons=["house", "mic", "volume-up", "file-earmark-text", "spellcheck", "soundwave", "info-circle"],
    default_index=0,
    orientation="horizontal",
    styles={
        "container": {"padding": "0!important", "background-color": "#f0f2f6"},
        "icon": {"font-size": "14px"},
        "nav-link": {"font-size": "14px", "text-align": "center", "margin": "0px",
                     "--hover-color": "#ddd"},
        "nav-link-selected": {"background-color": "#ff4b4b"},
    }
)

# ── Home page ────────────────────────────────────────────────────────────────
if page == "Home":
    st.title("🏠 Kia Orana! Welcome")
    st.write(
        "Welcome to the CIM NLP platform. "
        "Use the menu above to navigate between tools."
    )

# ── Transcription page ──────────────────────────────────────────────────────
elif page == "Transcription":
    st.title("🎙️ Cook Islands Māori Speech Recognition")
    st.write("Upload an audio file or record directly in your browser. "
             "You'll receive the transcription by email.")

    email = st.text_input("Your email address")

    tab_upload, tab_record = st.tabs(["📁 Upload a file", "🎤 Record audio"])

    def submit_audio(file_name: str, file_content: bytes, user_email: str):
        def send_request():
            try:
                requests.post(
                    st.secrets["ASR_URL"],
                    files={"file": (file_name, file_content, "audio/wav")},
                    data={"email": user_email},
                    timeout=3600,
                )
            except Exception:
                pass

        thread = threading.Thread(target=send_request, daemon=True)
        thread.start()

    with tab_upload:
        uploaded = st.file_uploader("Choose an audio file", type=["wav"])

        if st.button("Transcribe uploaded file", key="btn_upload"):
            if not email:
                st.error("Please enter your email address.")
            elif not uploaded:
                st.error("Please upload a WAV file.")
            else:
                file_content = uploaded.read()
                submit_audio(uploaded.name, file_content, email)
                st.success(
                    "✅ Your file has been submitted! You will receive an email "
                    "when processing begins, and another when your transcription "
                    "is ready."
                )

    with tab_record:
        recording = st.audio_input("Click the microphone to start recording")

        if st.button("Transcribe recording", key="btn_record"):
            if not email:
                st.error("Please enter your email address.")
            elif not recording:
                st.error("Please make a recording first.")
            else:
                file_content = recording.read()
                submit_audio("recording.wav", file_content, email)
                st.success(
                    "✅ Your recording has been submitted! You will receive an "
                    "email when processing begins, and another when your "
                    "transcription is ready."
                )

# ── Voice Generation page ───────────────────────────────────────────────────
elif page == "Voice Generation":
    st.title("🔊 Cook Islands Māori TTS")

    # Callbacks for special character buttons
    def add_char(char):
        st.session_state.user_text = st.session_state.user_text + char
        st.session_state.input_key += 1

    def on_text_change():
        st.session_state.user_text = st.session_state[f"text_input_{st.session_state.input_key}"]

    # Text input with dynamic key
    st.text_input(
        "Enter your text:",
        value=st.session_state.user_text,
        key=f"text_input_{st.session_state.input_key}",
        on_change=on_text_change
    )

    # Special character buttons
    st.caption("Insert special characters:")
    special_chars = ['ā', 'ē', 'ī', 'ō', 'ū', 'ꞌ']
    cols = st.columns(len(special_chars))
    for idx, char in enumerate(special_chars):
        with cols[idx]:
            st.button(char, key=f"btn_char_{idx}", use_container_width=True,
                      on_click=add_char, args=(char,))

    st.write("")

    # Generate button
    button_text = "Please wait..." if st.session_state.processing else "Generate audio"
    button_clicked = st.button(button_text, disabled=st.session_state.processing)

    if button_clicked:
        st.session_state.audio_bytes = None
        st.session_state.error_message = None
        st.session_state.processing = True
        st.rerun()

    if st.session_state.processing:
        try:
            api_url = st.secrets["TTS_URL"]

            response = requests.post(
                api_url,
                json={"text": st.session_state.user_text},
                timeout=60
            )

            if response.ok:
                st.session_state.audio_bytes = response.content
            else:
                st.session_state.error_message = (
                    f"HTTP Error {response.status_code}: {response.reason}\n"
                    f"Response body: {response.text}"
                )
        except requests.exceptions.ConnectionError as e:
            st.session_state.error_message = f"Connection error: {e}"
        except requests.exceptions.Timeout as e:
            st.session_state.error_message = f"Request timed out: {e}"
        except Exception as e:
            st.session_state.error_message = f"Unexpected error: {type(e).__name__}: {e}"
        finally:
            st.session_state.processing = False
            st.rerun()

    # Display results
    if st.session_state.audio_bytes:
        st.success("Audio generated!")
        st.audio(st.session_state.audio_bytes, format='audio/wav')
        st.download_button(
            label="Download WAV",
            data=st.session_state.audio_bytes,
            file_name="output.wav",
            mime="audio/wav"
        )

    if st.session_state.error_message:
        st.error(st.session_state.error_message)

# ── Parsing page ─────────────────────────────────────────────────────────────
elif page == "Parsing":
    st.title("📄 Parsing")
    st.write("This feature is coming soon.")

# ── Spell Checking page ─────────────────────────────────────────────────────
elif page == "Spell Checking":
    st.title("✏️ Spell Checking")
    st.write("This feature is coming soon.")

# ── Forced Alignment page ───────────────────────────────────────────────────
elif page == "Forced Alignment":
    st.title("🔊 Forced Alignment")
    st.write("This feature is coming soon.")

# ── About page ───────────────────────────────────────────────────────────────
elif page == "About":
    st.title("About the Project")
    st.markdown("The speech recognition (transcription) uses a [Wav2Vec2-XLSR](https://huggingface.co/docs/transformers/en/model_doc/xlsr_wav2vec2) model that transforms an audio recording in Cook Islands Māori into a text transcription of the words in the recording.")
    st.markdown("The model was developed by Rolando Coto-Solano, Sally Akevai Nicholas, and students from Dartmouth College. You can read more about the project here: [Development of Automatic Speech Recognition for the Documentation of Cook Islands Māori](https://aclanthology.org/2022.lrec-1.412).")
    st.markdown("The text-to-speech (voice generation) uses a [FastSpeech2](https://arxiv.org/abs/2006.04558) model that transforms text in Cook Islands Māori into a synthetically generated voice recording.")
    st.markdown("The model was developed by Jesyn James, Sally Akevai Nicholas, Rolando Coto-Solano, and students from University of Auckland. You can read more about the project here: [Development of Community-Oriented Text-to-Speech Models for Māori ꞌAvaiki Nui (Cook Islands Māori)](https://aclanthology.org/2024.lrec-main.432/)")
    st.write("This is part of a larger project by Sally Akevai Nicholas to document the Cook Islands Māori language.")
