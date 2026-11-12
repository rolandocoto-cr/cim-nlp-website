import requests
import streamlit as st
import threading
import base64
from streamlit_option_menu import option_menu

st.set_page_config(page_title="Cook Islands Māori NLP", initial_sidebar_state="collapsed")

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

# ── Initialize Parsing session state ─────────────────────────────────────────
if 'parse_processing' not in st.session_state:
    st.session_state.parse_processing = False
if 'parse_png' not in st.session_state:
    st.session_state.parse_png = None
if 'parse_conllu' not in st.session_state:
    st.session_state.parse_conllu = None
if 'parse_error' not in st.session_state:
    st.session_state.parse_error = None
if 'parse_text' not in st.session_state:
    st.session_state.parse_text = "E moe ana te kiorengiao"
if 'parse_input_key' not in st.session_state:
    st.session_state.parse_input_key = 0

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
    st.write("Upload an audio file, share a Google Drive link, or record directly in your browser. "
             "You'll receive the transcription by email.")

    email = st.text_input("Your email address")

    tab_upload, tab_gdrive, tab_record = st.tabs(["📁 Upload a file", "🔗 Google Drive link", "🎤 Record audio"])

    # ── DEBUG MODE ───────────────────────────────────────────────────────────
    # Requests are sent synchronously and every result/error is shown on screen.
    # Revert to the threaded version once the problem is found.
    DEBUG_TIMEOUT = 60  # seconds to wait for the server before giving up

    with st.expander("🛠️ Debug info", expanded=True):
        try:
            from urllib.parse import urlparse
            _parsed = urlparse(st.secrets["ASR_URL"])
            # Show only scheme + host so the full URL isn't exposed on the page
            st.write(f"ASR_URL is set → `{_parsed.scheme}://{_parsed.netloc}/…`")
        except Exception as e:
            st.error(f"ASR_URL could not be read from secrets: {type(e).__name__}: {e}")

    def show_response(response):
        st.write(f"**HTTP status:** {response.status_code} {response.reason}")
        st.write(f"**Content-Type:** {response.headers.get('Content-Type', '(none)')}")
        st.write("**Response body (first 2000 chars):**")
        st.code(response.text[:2000] or "(empty)", language=None)

    def debug_post(**kwargs):
        try:
            with st.spinner("Contacting ASR server…"):
                response = requests.post(st.secrets["ASR_URL"], timeout=DEBUG_TIMEOUT, **kwargs)
            show_response(response)
            return response.ok
        except requests.exceptions.Timeout:
            st.warning(
                f"No reply within {DEBUG_TIMEOUT} s. If the server only replies after it "
                "finishes transcribing, this may be normal; check whether the emails arrive."
            )
        except requests.exceptions.ConnectionError as e:
            st.error(f"Connection error (server unreachable or URL wrong): {e}")
        except Exception as e:
            st.error(f"Unexpected error: {type(e).__name__}: {e}")
        return False

    def submit_audio(file_name: str, file_content: bytes, user_email: str):
        st.write(f"Sending **{file_name}** ({len(file_content):,} bytes) as multipart form data…")
        return debug_post(
            files={"file": (file_name, file_content, "audio/wav")},
            data={"email": user_email},
        )

    def submit_gdrive(gdrive_url: str, user_email: str):
        st.write("Sending Google Drive link as JSON…")
        return debug_post(json={"gdrive_url": gdrive_url, "email": user_email})

    with tab_upload:
        st.info("⚠️ Maximum file size: **10 MB**. For larger files, use the **Google Drive link** tab.")
        uploaded = st.file_uploader("Choose an audio file", type=["wav"])

        if st.button("Transcribe uploaded file", key="btn_upload"):
            if not email:
                st.error("Please enter your email address.")
            elif not uploaded:
                st.error("Please upload a WAV file.")
            else:
                file_content = uploaded.read()
                if submit_audio(uploaded.name, file_content, email):
                    st.success(
                    "✅ Your file has been submitted! You will receive an email "
                    "when processing begins, and another when your transcription "
                    "is ready."
                )

    with tab_gdrive:
        st.write("Share your audio file via Google Drive. Make sure the file is set to "
                 "**\"Anyone with the link can view\"**.")
        st.markdown(
            "**How to get a shareable link:**\n"
            "1. Right-click your file in Google Drive\n"
            "2. Click **Share** → **General access** → **Anyone with the link**\n"
            "3. Copy the link and paste it below"
        )
        gdrive_link = st.text_input("Google Drive link", placeholder="https://drive.google.com/file/d/...")

        if st.button("Transcribe from Google Drive", key="btn_gdrive"):
            if not email:
                st.error("Please enter your email address.")
            elif not gdrive_link:
                st.error("Please enter a Google Drive link.")
            elif "drive.google.com" not in gdrive_link and "docs.google.com" not in gdrive_link:
                st.error("Please enter a valid Google Drive link.")
            else:
                if submit_gdrive(gdrive_link, email):
                    st.success(
                    "✅ Your Google Drive link has been submitted! You will receive an email "
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
                if submit_audio("recording.wav", file_content, email):
                    st.success(
                    "✅ Your recording has been submitted! You will receive an "
                    "email when processing begins, and another when your "
                    "transcription is ready."
                )

# ── Voice Generation page ───────────────────────────────────────────────────
elif page == "Voice Generation":
    st.title("🔊 Cook Islands Māori TTS")

    def add_char(char):
        st.session_state.user_text = st.session_state.user_text + char
        st.session_state.input_key += 1

    def on_text_change():
        st.session_state.user_text = st.session_state[f"text_input_{st.session_state.input_key}"]

    st.text_input(
        "Enter your text:",
        value=st.session_state.user_text,
        key=f"text_input_{st.session_state.input_key}",
        on_change=on_text_change
    )

    st.caption("Insert special characters:")
    special_chars = ['ā', 'ē', 'ī', 'ō', 'ū', 'ꞌ']
    cols = st.columns(len(special_chars))
    for idx, char in enumerate(special_chars):
        with cols[idx]:
            st.button(char, key=f"btn_char_{idx}", use_container_width=True,
                      on_click=add_char, args=(char,))

    st.write("")

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
    st.title("📄 Cook Islands Māori Parser")
    st.write("Enter a sentence in Cook Islands Māori and get a dependency parse tree.")

    def add_parse_char(char):
        st.session_state.parse_text = st.session_state.parse_text + char
        st.session_state.parse_input_key += 1

    def on_parse_text_change():
        st.session_state.parse_text = st.session_state[f"parse_input_{st.session_state.parse_input_key}"]

    st.text_input(
        "Enter your sentence:",
        value=st.session_state.parse_text,
        key=f"parse_input_{st.session_state.parse_input_key}",
        on_change=on_parse_text_change
    )

    st.caption("Insert special characters:")
    special_chars = ['ā', 'ē', 'ī', 'ō', 'ū', 'ꞌ']
    cols = st.columns(len(special_chars))
    for idx, char in enumerate(special_chars):
        with cols[idx]:
            st.button(char, key=f"btn_parse_char_{idx}", use_container_width=True,
                      on_click=add_parse_char, args=(char,))

    st.write("")

    parse_button_text = "Please wait..." if st.session_state.parse_processing else "Parse sentence"
    parse_clicked = st.button(parse_button_text, disabled=st.session_state.parse_processing)

    if parse_clicked:
        st.session_state.parse_png = None
        st.session_state.parse_conllu = None
        st.session_state.parse_error = None
        st.session_state.parse_processing = True
        st.rerun()

    if st.session_state.parse_processing:
        try:
            parse_url = st.secrets["PARSE_URL"]
            response = requests.post(
                parse_url,
                json={"text": st.session_state.parse_text},
                timeout=120
            )
            if response.ok:
                data = response.json()
                st.session_state.parse_conllu = data.get("conllu", "")
                png_b64 = data.get("png", "")
                if png_b64:
                    st.session_state.parse_png = base64.b64decode(png_b64)
            else:
                try:
                    err = response.json().get("error", response.text)
                except Exception:
                    err = response.text
                st.session_state.parse_error = f"HTTP Error {response.status_code}: {err}"
        except requests.exceptions.ConnectionError as e:
            st.session_state.parse_error = f"Connection error: {e}"
        except requests.exceptions.Timeout as e:
            st.session_state.parse_error = f"Request timed out: {e}"
        except Exception as e:
            st.session_state.parse_error = f"Unexpected error: {type(e).__name__}: {e}"
        finally:
            st.session_state.parse_processing = False
            st.rerun()

    if st.session_state.parse_png:
        st.success("Parse complete!")
        st.image(st.session_state.parse_png, caption="Dependency Parse Tree", use_container_width=True)

    if st.session_state.parse_conllu:
        st.download_button(
            label="Download CoNLL-U parse",
            data=st.session_state.parse_conllu,
            file_name="parse.conllu",
            mime="text/plain"
        )
        with st.expander("View CoNLL-U text"):
            st.code(st.session_state.parse_conllu, language=None)

    if st.session_state.parse_error:
        st.error(st.session_state.parse_error)

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
    st.markdown("The dependency parser uses [UDPipe 2](https://ufal.mff.cuni.cz/udpipe/2) to produce Universal Dependencies parses of Cook Islands Māori sentences.")
    st.write("This is part of a larger project by Sally Akevai Nicholas to document the Cook Islands Māori language.")