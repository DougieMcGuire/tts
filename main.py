from flask import Flask, request, Response, jsonify, send_file
import os
import whisper
import edge_tts
import asyncio
import tempfile
import subprocess
import json
import uuid
from werkzeug.utils import secure_filename
import re

app = Flask(__name__)

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
TEMP_FOLDER = 'temp'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

# Load Whisper model
whisper_model = whisper.load_model("base")

@app.route('/')
def index():
    return '''
    <html>
        <head>
            <title>Audio/Video Processing API</title>
            <style>
                body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
                h1, h2 { color: #333; }
                form { margin-bottom: 30px; padding: 20px; border: 1px solid #ddd; border-radius: 5px; }
                input, textarea { margin: 10px 0; padding: 8px; width: 100%; }
                button { background-color: #4CAF50; color: white; padding: 10px 15px; border: none; cursor: pointer; }
                button:hover { background-color: #45a049; }
            </style>
        </head>
        <body>
            <h1>Audio/Video Processing API</h1>
            
            <h2>Speech to Text (Whisper)</h2>
            <form action="/whisper" method="post" enctype="multipart/form-data">
                <p>Upload MP3 file to transcribe:</p>
                <input type="file" name="audio" accept=".mp3">
                <button type="submit">Transcribe</button>
            </form>
            
            <h2>Text to Speech (Edge-TTS)</h2>
            <form action="/tts" method="post">
                <p>Enter text to convert to speech:</p>
                <textarea name="text" rows="5" cols="50"></textarea>
                <button type="submit">Generate Speech</button>
            </form>
            
            <h2>FFMPEG Video Processing</h2>
            <form action="/ffmpeg" method="post" enctype="multipart/form-data">
                <p>Upload video file:</p>
                <input type="file" name="video">
                <p>Enter FFMPEG command (use INPUT for input file and OUTPUT for output file):</p>
                <textarea name="command" rows="3" cols="50">-i INPUT -c:v libx264 -crf 23 -preset medium OUTPUT</textarea>
                <button type="submit">Process Video</button>
            </form>
        </body>
    </html>
    '''

@app.route('/whisper', methods=['POST'])
def process_whisper():
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
    
    audio_file = request.files['audio']
    if audio_file.filename == '':
        return jsonify({"error": "No audio file selected"}), 400
    
    if not audio_file.filename.endswith('.mp3'):
        return jsonify({"error": "Only MP3 files are supported"}), 400
    
    # Save the uploaded file
    filename = secure_filename(audio_file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    audio_file.save(filepath)
    
    try:
        # Process the audio with Whisper
        result = whisper_model.transcribe(filepath, word_timestamps=True)
        
        # Generate SRT format
        srt_content = generate_srt(result)
        
        # Cleanup
        os.remove(filepath)
        
        # Return SRT as response
        return Response(srt_content, mimetype='text/plain')
    
    except Exception as e:
        # Cleanup in case of error
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({"error": str(e)}), 500

def generate_srt(result):
    """Generate SRT format from Whisper result with word timestamps."""
    segments = []
    segment_id = 1
    
    for segment in result["segments"]:
        if "words" in segment:
            # Process words in each segment
            for word in segment["words"]:
                start_time = word["start"]
                end_time = word["end"]
                text = word["word"].strip()
                
                if text:  # Skip empty words
                    start_str = format_timestamp(start_time)
                    end_str = format_timestamp(end_time)
                    segments.append(f"{segment_id}\n{start_str} --> {end_str}\n{text}\n")
                    segment_id += 1
    
    return "\n".join(segments)

def format_timestamp(seconds):
    """Convert seconds to SRT timestamp format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    seconds %= 3600
    minutes = int(seconds // 60)
    seconds %= 60
    milliseconds = int((seconds - int(seconds)) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{int(seconds):02d},{milliseconds:03d}"

@app.route('/tts', methods=['POST'])
def process_tts():
    text = request.form.get('text', '')
    if not text:
        return jsonify({"error": "No text provided"}), 400
    
    try:
        # Generate audio using edge-tts
        output_file = os.path.join(TEMP_FOLDER, f"{uuid.uuid4()}.mp3")
        
        # Run edge-tts asynchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(generate_speech(text, output_file))
        
        # Return the audio file
        return send_file(output_file, mimetype='audio/mpeg', as_attachment=True, 
                        download_name='tts_output.mp3', 
                        after_this_request=lambda _: cleanup_file(output_file))
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

async def generate_speech(text, output_path):
    """Generate speech using edge-tts with custom voice settings."""
    voice = "en-US-EricNeural"
    rate = "+9%"
    pitch = "-5Hz"
    
    communicate = edge_tts.Communicate(text, voice)
    # Apply rate and pitch adjustments
    communicate._rate = rate
    communicate._pitch = pitch
    
    await communicate.save(output_path)

def cleanup_file(file_path):
    """Clean up temporary files."""
    if os.path.exists(file_path):
        os.remove(file_path)
    return True

@app.route('/ffmpeg', methods=['POST'])
def process_ffmpeg():
    if 'video' not in request.files:
        return jsonify({"error": "No video file provided"}), 400
    
    video_file = request.files['video']
    if video_file.filename == '':
        return jsonify({"error": "No video file selected"}), 400
    
    ffmpeg_cmd = request.form.get('command', '')
    if not ffmpeg_cmd:
        return jsonify({"error": "No FFMPEG command provided"}), 400
    
    # Save the uploaded video file
    video_filename = secure_filename(video_file.filename)
    input_path = os.path.join(UPLOAD_FOLDER, video_filename)
    video_file.save(input_path)
    
    # Create output path
    output_filename = f"output_{uuid.uuid4()}_{os.path.splitext(video_filename)[0]}.mp4"
    output_path = os.path.join(TEMP_FOLDER, output_filename)
    
    try:
        # Replace placeholders in command
        ffmpeg_cmd = ffmpeg_cmd.replace("INPUT", input_path).replace("OUTPUT", output_path)
        
        # Build the complete ffmpeg command
        cmd = f"ffmpeg {ffmpeg_cmd}"
        
        # Execute the FFmpeg command
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            return jsonify({
                "error": "FFMPEG processing failed",
                "details": stderr.decode('utf-8', errors='replace')
            }), 500
        
        # Return the processed video
        return send_file(output_path, as_attachment=True, 
                        download_name=f"processed_{video_filename}", 
                        after_this_request=lambda _: cleanup_files([input_path, output_path]))
    
    except Exception as e:
        # Clean up files in case of error
        cleanup_files([input_path, output_path])
        return jsonify({"error": str(e)}), 500

def cleanup_files(file_paths):
    """Clean up multiple files."""
    for path in file_paths:
        if os.path.exists(path):
            os.remove(path)
    return True

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
