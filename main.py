from flask import Flask, request, send_file
import edge_tts
import asyncio
import os

app = Flask(__name__)

@app.route('/generate_mp3', methods=['POST'])
async def generate_mp3():
    text = request.json.get('text')
    if not text:
        return {"error": "Text is required"}, 400
    
    # Path for saving the MP3 file
    mp3_filename = 'output.mp3'
    
    # Generate MP3 using EdgeTTS
    communicate = edge_tts.Communicate(text, "en-US-JennyNeural")
    await communicate.save(mp3_filename)

    # Return the MP3 file as a response
    return send_file(mp3_filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
