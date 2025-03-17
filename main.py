from flask import Flask, request, Response, jsonify, send_file
import os
import tempfile
import subprocess
import json
import uuid
from werkzeug.utils import secure_filename
import asyncio
import whisper
import edge_tts

app = Flask(__name__)

# Configure folders
UPLOAD_FOLDER = 'uploads'
TEMP_FOLDER = 'temp'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

# Load Whisper model
whisper_model = whisper.load_model("base")

@app.route('/whisper', methods=['POST'])
def process_whisper():
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
    
    audio_file = request.files['audio']
    if audio_file.filename == '':
        return jsonify({"error": "No audio file selected"}), 400
    
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
                        download_name='tts_output.mp3')
    
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
                        download_name=f"processed_{video_filename}")
    
    except Exception as e:
        # Clean up files in case of error
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
