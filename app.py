import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
import re
from gradio_client import Client
from deep_translator import GoogleTranslator
import os

def extract_video_id(url):
    patterns = [
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=([_\-a-zA-Z0-9]{11})',
        r'(?:https?:\/\/)?(?:www\.)?youtu\.be\/([_\-a-zA-Z0-9]{11})'
    ]
    for pattern in patterns:
        match = re.match(pattern, url)
        if match:
            return match.group(1)
    return None

def download_youtube_transcript(video_url):
    video_id = extract_video_id(video_url)
    if not video_id:
        st.error("Invalid YouTube URL.")
        return None

    try:
        transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = None
        for transcript_obj in transcripts:
            try:
                transcript = transcript_obj.fetch()
                break
            except Exception:
                continue

        if not transcript:
            st.error("Transcript not available for this video.")
            return None

        formatter = TextFormatter()
        formatted_transcript = formatter.format_transcript(transcript)
        return formatted_transcript
    except Exception as e:
        st.error(f"An error occurred: {e}")
        return None

def translate_text(text, dest_language):
    translator = GoogleTranslator(source='auto', target=dest_language)
    chunk_size = 500
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    translated_chunks = [translator.translate(chunk) for chunk in chunks]
    return ' '.join(translated_chunks)

def generate_mcqs(transcript, num_questions=10, language='en'):
    client = Client(os.getenv("CLIENT"))
    prompt = f"""
    Based on the following transcript, generate exactly {num_questions} multiple-choice questions (MCQs) with 4 options each.
    Ensure the questions cover various aspects of the video content to thoroughly check user understanding.
    Format each question as follows:
    Q: [Question]
    A) [Option A]
    B) [Option B]
    C) [Option C]
    D) [Option D]
    Correct Answer: [A/B/C/D]

    Transcript:
    {transcript}
    """

    result = client.predict(prompt=prompt, api_name="/predict")
    return result

def parse_mcqs(mcqs_text):
    questions = []
    current_question = {}
    for line in mcqs_text.split('\n'):
        line = line.strip()
        if line.startswith('Q:'):
            if current_question:
                questions.append(current_question)
            current_question = {'question': line[2:].strip(), 'options': []}
        elif line.startswith(('A)', 'B)', 'C)', 'D)')):
            current_question['options'].append(line)
        elif line.startswith('Correct Answer:'):
            current_question['correct_answer'] = line.split(':')[1].strip()
    if current_question:
        questions.append(current_question)
    return questions

def reset_state():
    for key in ['transcript', 'translated_transcript', 'questions', 'answers', 'submitted']:
        if key in st.session_state:
            del st.session_state[key]
    st.session_state['video_url'] = ""
    st.session_state['num_questions'] = 10

def display_mcqs():
    if st.session_state['questions']:
        for i, q in enumerate(st.session_state['questions']):
            st.subheader(f"Q{i+1}: {q['question']}")
            options = [opt.split(') ')[1] for opt in q['options']]
            answer = st.radio("Select an answer:", options, key=f"q{i}", index=None)
            st.session_state['answers'][i] = answer

        if st.button("Submit Answers"):
            st.session_state['submitted'] = True

        if st.session_state['submitted']:
            correct_count = 0
            for i, q in enumerate(st.session_state['questions']):
                st.subheader(f"Q{i+1}: {q['question']}")
                correct_option = q['correct_answer']
                selected_option = st.session_state['answers'][i]

                try:
                    correct_answer = next(opt for opt in q['options'] if opt.startswith(correct_option))
                    correct_answer = correct_answer.split(') ')[1]
                    if selected_option:
                        if selected_option == correct_answer:
                            st.success("Correct!")
                            correct_count += 1
                        else:
                            st.error(f"Incorrect. The correct answer is {correct_answer}")
                    else:
                        st.warning("You didn't answer this question.")
                except StopIteration:
                    st.error("There was an error with the correct answer. Please try again.")

            total_questions = len(st.session_state['questions'])
            score_percentage = (correct_count / total_questions) * 100
            st.write(f"Your score: {correct_count}/{total_questions} ({score_percentage:.2f}%)")
            if score_percentage >= 80:
                st.success("Great job! You have a good understanding of the video content.")
            elif score_percentage >= 60:
                st.info("Good effort! You might want to review some parts of the video.")
            else:
                st.warning("You might need to watch the video again to improve your understanding.")

    if st.button("Start Again"):
        reset_state()
        st.experimental_rerun()

# Streamlit App
st.set_page_config(page_title="YouTube Video MCQ Generator", layout="wide")
st.title("YouTube Video MCQ Generator")

# Initialize session state variables
if 'language' not in st.session_state:
    st.session_state['language'] = "English"
if 'video_url' not in st.session_state:
    st.session_state['video_url'] = ""
if 'num_questions' not in st.session_state:
    st.session_state['num_questions'] = 10
if 'submitted' not in st.session_state:
    st.session_state['submitted'] = False
if 'questions' not in st.session_state:
    st.session_state['questions'] = None

# Language selection
st.session_state['language'] = st.radio("Select language for questions:", ["English", "Hindi"])
language_code = 'en' if st.session_state['language'] == "English" else 'hi'

# Input for YouTube URL
st.session_state['video_url'] = st.text_input("Enter YouTube Video URL:", value=st.session_state['video_url'])

if st.session_state['video_url']:
    if 'transcript' not in st.session_state:
        transcript = download_youtube_transcript(st.session_state['video_url'])
        if transcript:
            st.session_state['transcript'] = transcript

    if 'translated_transcript' not in st.session_state and 'transcript' in st.session_state:
        with st.spinner("Translating transcript..."):
            translated_transcript = translate_text(st.session_state['transcript'], language_code)
            st.session_state['translated_transcript'] = translated_transcript

    if 'translated_transcript' in st.session_state:
        st.success("Transcript downloaded and translated successfully!")

        st.session_state['num_questions'] = st.slider("Number of questions to generate:", min_value=5, max_value=20, value=st.session_state['num_questions'])

        if st.button("Generate MCQs"):
            with st.spinner(f"Generating {st.session_state['num_questions']} questions in {st.session_state['language']}..."):
                mcqs_text = generate_mcqs(st.session_state['translated_transcript'], st.session_state['num_questions'], st.session_state['language'])
                questions = parse_mcqs(mcqs_text)
                st.session_state['questions'] = questions
                st.session_state['answers'] = [''] * len(questions)
                st.session_state['submitted'] = False

if st.session_state['questions']:
    display_mcqs()
