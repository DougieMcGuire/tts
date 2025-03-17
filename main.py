from flask import Flask, request, Response, jsonify, send_file
import os
import tempfile
import subprocess
import json
import uuid
from werkzeug.utils import secure_filename
import asyncio
import edge_tts

app = Flask(__name__)

# Configure folders
UPLOAD_FOLDER = 'uploads'
TEMP_FOLDER = 'temp'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

@app.route('/')
def index():
    return "API is running. Use /tts or /ffmpeg endpoints."

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

# Added cleanup function to delete temporary files after processing
@app.after_request
def cleanup(response):
    for folder in [UPLOAD_FOLDER, TEMP_FOLDER]:
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            try:
                # Check if file is more than 5 minutes old
                if os.path.isfile(file_path) and (time.time() - os.path.getmtime(file_path)) > 300:
                    os.remove(file_path)
            except Exception as e:
                print(f"Error cleaning up file {file_path}: {e}")
    return response

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
