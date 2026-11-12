import io
import json
import inspect
import time
import wave
import base64
import threading

import requests
import streamlit as st
from urllib3.filepost import encode_multipart_formdata
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
    st.title("🏠 Kia Orana! Welcome!")
    st.write(
        "Welcome to the CIM NLP platform. "
        "Use the menu above to navigate between tools."
    )

# ── Transcription page ──────────────────────────────────────────────────────
elif page == "Transcription":
    st.title("🎙️ Cook Islands Māori Speech Recognition")
    st.write("Upload an audio file, share a Google Drive link, or record directly in your browser. "
             "You'll receive the transcription by email.")

    MAX_UPLOAD_MB = 25            # keep in sync with server.maxUploadSize in .streamlit/config.toml
    MAX_RECORDING_SECONDS = 60
    UPLOAD_MAX_WAIT = 15 * 60     # give up if an upload hasn't finished after 15 minutes
    SERVER_GRACE_SECONDS = 5      # after upload, wait briefly in case the server rejects it right away

    email = st.text_input("Your email address")

    tab_upload, tab_gdrive, tab_record = st.tabs(["📁 Upload a file", "🔗 Google Drive link", "🎤 Record audio"])

    # ── DEBUG INFO (uncomment to check that ASR_URL is readable from secrets) ──
    # with st.expander("🛠️ Debug info", expanded=True):
    #     try:
    #         from urllib.parse import urlparse
    #         _parsed = urlparse(st.secrets["ASR_URL"])
    #         st.write(f"ASR_URL is set → `{_parsed.scheme}://{_parsed.netloc}/…`")
    #     except Exception as e:
    #         st.error(f"ASR_URL could not be read from secrets: {type(e).__name__}: {e}")

    class UploadTracker:
        """File-like wrapper around the request body that counts how many bytes have been sent."""
        def __init__(self, body: bytes):
            self._buf = io.BytesIO(body)
            self.total = len(body)
            self.sent = 0
            self.done = threading.Event()

        def read(self, size=-1):
            chunk = self._buf.read(size)
            self.sent += len(chunk)
            if self.sent >= self.total:
                self.done.set()
            return chunk

        def __len__(self):
            return self.total

    def send_to_asr(body: bytes, content_type: str, what: str) -> bool:
        """
        Send the request in a background thread (the server only replies after the
        transcription is finished), show upload progress, and return True once the
        upload has completed and the server hasn't rejected it.
        """
        try:
            asr_url = st.secrets["ASR_URL"]
        except Exception:
            st.error("The transcription service is not configured (ASR_URL missing). "
                     "Please contact the site administrator.")
            return False

        tracker = UploadTracker(body)
        result = {"status": None, "body": "", "error": None}
        finished = threading.Event()

        def worker():
            try:
                r = requests.post(
                    asr_url,
                    data=tracker,
                    headers={"Content-Type": content_type},
                    timeout=(30, 3600),
                )
                result["status"] = r.status_code
                result["body"] = r.text[:500]
            except Exception as e:
                result["error"] = f"{type(e).__name__}: {e}"
            finally:
                finished.set()

        threading.Thread(target=worker, daemon=True).start()

        total_mb = tracker.total / 1_000_000
        bar = st.progress(0.0, text=f"Sending {what}…")
        deadline = time.time() + UPLOAD_MAX_WAIT
        while not tracker.done.is_set() and not finished.is_set():
            if time.time() > deadline:
                bar.empty()
                st.error("The upload is taking too long. Please check your connection and try again.")
                return False
            frac = tracker.sent / tracker.total if tracker.total else 1.0
            bar.progress(min(frac, 1.0),
                         text=f"Sending {what}… {tracker.sent / 1_000_000:.1f} of {total_mb:.1f} MB")
            time.sleep(0.25)

        bar.progress(1.0, text=f"Upload complete ({total_mb:.1f} MB). Checking with the server…")
        finished.wait(timeout=SERVER_GRACE_SECONDS)
        bar.empty()

        if result["error"]:
            st.error(f"Could not reach the transcription service. Please try again later.\n\n"
                     f"Details: {result['error']}")
            return False
        if result["status"] is not None and not (200 <= result["status"] < 300):
            st.error(f"The transcription service rejected the request (HTTP {result['status']}).\n\n"
                     f"Details: {result['body'] or '(no details)'}")
            return False
        return True

    def submit_audio(file_name: str, file_content: bytes, user_email: str) -> bool:
        body, content_type = encode_multipart_formdata({
            "email": user_email,
            "file": (file_name, file_content, "audio/wav"),
        })
        return send_to_asr(body, content_type, "your audio")

    def submit_gdrive(gdrive_url: str, user_email: str) -> bool:
        body = json.dumps({"gdrive_url": gdrive_url, "email": user_email}).encode("utf-8")
        return send_to_asr(body, "application/json", "your Google Drive link")

    def wav_duration_seconds(data: bytes):
        """Length of a WAV file in seconds, or None if it can't be read."""
        try:
            with wave.open(io.BytesIO(data)) as w:
                return w.getnframes() / float(w.getframerate())
        except Exception:
            return None

    def show_started_message():
        st.success(
            "✅ Upload complete. The process has begun, please monitor your email. "
            "You will receive one email when processing starts and another "
            "when your transcription is ready (check your spam folder too)."
        )

    with tab_upload:
        st.info(f"⚠️ Maximum file size: **{MAX_UPLOAD_MB} MB**. "
                "For larger files, use the **Google Drive link** tab.")
        # Only one file per submission. Newer Streamlit versions accept a per-widget size
        # limit; older ones fall back to server.maxUploadSize in .streamlit/config.toml.
        uploader_kwargs = {"type": ["wav"], "accept_multiple_files": False}
        if "max_upload_size" in inspect.signature(st.file_uploader).parameters:
            uploader_kwargs["max_upload_size"] = MAX_UPLOAD_MB
        uploaded = st.file_uploader("Choose an audio file", **uploader_kwargs)

        if st.button("Transcribe uploaded file", key="btn_upload"):
            if not email:
                st.error("Please enter your email address.")
            elif not uploaded:
                st.error("Please upload a WAV file.")
            elif uploaded.size > MAX_UPLOAD_MB * 1024 * 1024:
                st.error(f"This file is {uploaded.size / (1024 * 1024):.1f} MB, which is over the "
                         f"{MAX_UPLOAD_MB} MB limit. Please use the **Google Drive link** tab instead.")
            else:
                if submit_audio(uploaded.name, uploaded.getvalue(), email):
                    show_started_message()

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
                    show_started_message()

    with tab_record:
        st.info(f"⏱️ Recordings are limited to **{MAX_RECORDING_SECONDS} seconds**. "
                "Longer recordings will not be sent. For longer audio, use the "
                "**Upload a file** or **Google Drive link** tab.")
        recording = st.audio_input("Click the microphone to start recording")

        duration = None
        if recording:
            file_content = recording.getvalue()
            duration = wav_duration_seconds(file_content)
            if duration is not None:
                if duration > MAX_RECORDING_SECONDS:
                    st.warning(f"Your recording is {duration:.0f} seconds long, which is over the "
                               f"{MAX_RECORDING_SECONDS}-second limit. Please record a shorter clip.")
                else:
                    st.caption(f"Recording length: {duration:.0f} seconds")

        if st.button("Transcribe recording", key="btn_record"):
            if not email:
                st.error("Please enter your email address.")
            elif not recording:
                st.error("Please make a recording first.")
            elif duration is not None and duration > MAX_RECORDING_SECONDS:
                st.error(f"Recordings must be {MAX_RECORDING_SECONDS} seconds or shorter. "
                         "Please record again.")
            else:
                if submit_audio("recording.wav", file_content, email):
                    show_started_message()

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
