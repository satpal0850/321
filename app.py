from flask import Flask, request, render_template, flash, send_from_directory, redirect, url_for, jsonify, Response
import yt_dlp
import logging
import re
import os
import requests
import subprocess

# Setup basic logging
logging.basicConfig(level=logging.INFO)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Check if FFmpeg is available
def check_ffmpeg():
    try:
        subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(['ffprobe', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

FFMPEG_AVAILABLE = check_ffmpeg()

# Function to sanitize filenames by removing illegal characters
def sanitize_filename(filename):
    """Remove illegal characters from filename."""
    return re.sub(r'[\\/*?:"<>|]', "", filename)

# Route for the home page
@app.route('/', methods=['GET'])
def index():
    return render_template("index.html")

# Route for the Instagram 
@app.route('/instagram', methods=['GET'])
def instagram():
    return render_template("instagram.html")

# Redirect /index.html to /
@app.route('/index.html')
def redirect_to_root():
    return redirect(url_for('index'), code=301)

# Route to serve the robots.txt file
@app.route('/robots.txt')
def robots():
    return send_from_directory('.', 'robots.txt')

# Route to serve the sitemap.xml file
@app.route('/sitemap.xml')
def sitemap():
    return send_from_directory('.', 'sitemap.xml')

# Route for direct video download
@app.route('/direct-download', methods=['GET'])
def direct_download():
    video_url = request.args.get('video_url', '')
    filename = request.args.get('filename', 'video.mp4')
    is_audio = request.args.get('audio', 'false') == 'true'
    
    if not video_url:
        return "Invalid URL", 400
    
    try:
        if is_audio:
            if not FFMPEG_AVAILABLE:
                return "Audio download requires FFmpeg which is not installed on the server", 400

            # For audio download, we need to extract audio using yt-dlp
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'outtmpl': filename.replace('.mp4', '.mp3'),
                'quiet': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                temp_filename = ydl.prepare_filename(info).replace('.webm', '.mp3').replace('.m4a', '.mp3')
                
                def generate():
                    with open(temp_filename, 'rb') as f:
                        while chunk := f.read(1024 * 1024):  # 1MB chunks
                            yield chunk
                    os.remove(temp_filename)  # Clean up after download
                
                headers = {
                    'Content-Disposition': f'attachment; filename="{filename.replace(".mp4", ".mp3")}"',
                    'Content-Type': 'audio/mpeg'
                }
                
                return Response(generate(), headers=headers)
        else:
            # For video download, stream directly
            headers = {
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': 'video/mp4'
            }
            
            response = requests.get(video_url, stream=True)
            return Response(
                response.iter_content(chunk_size=1024),
                headers=headers,
                content_type=response.headers['content-type']
            )
    except Exception as e:
        return str(e), 500

# Route to handle video download
@app.route('/download', methods=['POST'])
def download():
    video_url = request.form.get('url', '').strip()

    if not video_url:
        return jsonify({'error': 'Please enter a video URL.'}), 400

    try:
        # Options for yt-dlp to get info
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4',  # Ensure the final output is mp4
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
        }

        # Downloading the video info
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(video_url, download=False)
            
            # Get the best format that includes both video and audio
            best_format = None
            for f in info_dict.get('formats', [info_dict]):
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                    best_format = f
                    break
            
            # If no combined format found, try to find separate video and audio streams
            if not best_format:
                video_format = None
                audio_format = None
                
                # Find best video stream
                for f in info_dict.get('formats', [info_dict]):
                    if f.get('vcodec') != 'none' and (not video_format or f.get('height', 0) > video_format.get('height', 0)):
                        video_format = f
                
                # Find best audio stream
                for f in info_dict.get('formats', [info_dict]):
                    if f.get('acodec') != 'none' and (not audio_format or f.get('abr', 0) > audio_format.get('abr', 0)):
                        audio_format = f
                
                if video_format and audio_format:
                    # Create a merged format entry
                    best_format = {
                        'url': f"{video_format['url']}+{audio_format['url']}",
                        'ext': 'mp4',
                        'width': video_format.get('width'),
                        'height': video_format.get('height'),
                        'vcodec': video_format.get('vcodec'),
                        'acodec': audio_format.get('acodec')
                    }
                else:
                    return jsonify({'error': 'Could not find both video and audio streams.'}), 400

            if not best_format or 'url' not in best_format:
                return jsonify({'error': 'Could not extract direct download URL. The video might be protected.'}), 400

            # Get thumbnail URL (try different quality thumbnails)
            thumbnail = info_dict.get('thumbnail')
            if not thumbnail:
                # Try to get any available thumbnail
                for thumb in ['thumbnails', 'thumbnail']:
                    if info_dict.get(thumb):
                        if isinstance(info_dict[thumb], list):
                            thumbnail = info_dict[thumb][-1]['url']  # Get highest quality thumbnail
                        else:
                            thumbnail = info_dict[thumb]
                        break

            # Prepare response data
            direct_url = best_format['url']
            title = info_dict.get('title', info_dict.get('id', 'video'))
            ext = best_format.get('ext', 'mp4')
            filename = sanitize_filename(f"{title}.{ext}")

            return jsonify({
                'video_url': direct_url,
                'filename': filename,
                'title': title,
                'thumbnail': thumbnail,
                'duration': info_dict.get('duration'),
                'width': best_format.get('width'),
                'height': best_format.get('height'),
                'has_audio': best_format.get('acodec') != 'none',
                'ffmpeg_available': FFMPEG_AVAILABLE
            })

    except yt_dlp.utils.DownloadError as e:
        return jsonify({'error': f"Download Error: {str(e)[:200]}"}), 400
    except Exception as e:
        return jsonify({'error': f"An error occurred: {str(e)[:200]}"}), 400

# Start the Flask app
if __name__ == '__main__':
    print("Flask app starting...")
    print("FFmpeg available:", FFMPEG_AVAILABLE)
    if not FFMPEG_AVAILABLE:
        print("Warning: FFmpeg not found. Audio downloads will not be available.")
    print("Open your browser and go to http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=10000)
