import os
import uuid
import subprocess
from flask import Flask, request, jsonify, send_file
import tempfile
import shutil

app = Flask(__name__)

# Configure upload folder
UPLOAD_FOLDER = '/tmp/ffmpeg_api'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/process', methods=['POST'])
def process_video():
    # Check if the POST request has the file part
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({'error': 'No video selected'}), 400
    
    # Check if ffmpeg command is provided
    if 'ffmpeg_command' not in request.form:
        return jsonify({'error': 'No FFmpeg command provided'}), 400
    
    ffmpeg_command = request.form['ffmpeg_command']
    
    # Create a unique session ID
    session_id = str(uuid.uuid4())
    session_dir = os.path.join(UPLOAD_FOLDER, session_id)
    os.makedirs(session_dir)
    
    try:
        # Save the uploaded video
        input_path = os.path.join(session_dir, "input" + os.path.splitext(file.filename)[1])
        file.save(input_path)
        
        # Prepare output path
        output_path = os.path.join(session_dir, "output" + os.path.splitext(file.filename)[1])
        
        # Replace input/output placeholders in the command
        ffmpeg_command = ffmpeg_command.replace("INPUT", input_path)
        ffmpeg_command = ffmpeg_command.replace("OUTPUT", output_path)
        
        # Execute FFmpeg command
        process = subprocess.Popen(
            ffmpeg_command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate()
        
        # Check if command was successful
        if process.returncode != 0:
            return jsonify({
                'error': 'FFmpeg processing failed',
                'stderr': stderr.decode('utf-8')
            }), 500
        
        # Return the processed file
        return send_file(output_path, as_attachment=True)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
    finally:
        # Clean up temporary files (optional, you might want to keep them for debugging)
        shutil.rmtree(session_dir, ignore_errors=True)

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
