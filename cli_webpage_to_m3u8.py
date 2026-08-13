import argparse
import os
import time
import threading
import subprocess
import re
import glob
from flask import Flask, send_from_directory
from playwright.sync_api import sync_playwright

app = Flask(__name__)

# جلوگیری از کش شدن ویدیوها در مرورگر
@app.route('/<path:filename>')
def serve_files(filename):
    response = send_from_directory('.', filename)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

def run_server():
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host='0.0.0.0', port=8080, threaded=True)

def start_tunnel():
    print("🌐 در حال برقراری اتصال به تونل عمومی SSH (localhost.run)...")
    process = subprocess.Popen(
        ['ssh', '-R', '80:localhost:8080', '-o', 'StrictHostKeyChecking=no', 'nokey@localhost.run'],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    for line in iter(process.stdout.readline, ''):
        if 'lhr.life' in line and 'admin' not in line:
            url_match = re.search(r'https://[a-zA-Z0-9-]+\.lhr\.life', line)
            if url_match:
                print(f"\n==================================================")
                print(f"🚀 لینک عمومی استریم M3U8 آماده شد:")
                print(f"🔗 {url_match.group(0)}/live.m3u8")
                print(f"==================================================\n")
                break

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--quality', required=True)
    parser.add_argument('--fps', required=True, type=int)
    parser.add_argument('--duration', required=True, type=int)
    args = parser.parse_args()

    qualities = {
        '240p': (426, 240, '500k'),
        '360p': (640, 360, '800k'),
        '480p': (854, 480, '1200k'),
        '720p': (1280, 720, '2500k'),
        '1080p': (1920, 1080, '4500k'),
        '1440p': (2560, 1440, '9000k')
    }
    
    width, height, bitrate = qualities.get(args.quality, qualities['720p'])
    fps = args.fps

    # پاک‌سازی فایل‌های استریم قبلی
    for f in glob.glob("*.ts") + glob.glob("*.m3u8"):
        try:
            os.remove(f)
        except:
            pass

    # روشن کردن سرور و تونل در پس‌زمینه
    threading.Thread(target=run_server, daemon=True).start()
    threading.Thread(target=start_tunnel, daemon=True).start()

    # تنظیمات فوق‌سریع برای جلوگیری از لگ در سرورهای ضعیف گیت‌هاب
    ffmpeg_cmd = [
        'ffmpeg', '-y', 
        '-f', 'image2pipe', 
        '-vcodec', 'mjpeg', 
        '-r', str(fps),
        '-i', '-',
        '-c:v', 'libx264', 
        '-preset', 'ultrafast',       # سرعت حداکثری انکود
        '-tune', 'zerolatency',       # حذف تاخیر
        '-b:v', bitrate, 
        '-maxrate', bitrate, 
        '-bufsize', str(int(bitrate.replace('k',''))*2) + 'k',
        '-pix_fmt', 'yuv420p', 
        '-g', str(fps * 2),           # تولید کلیدفریم هر ۲ ثانیه برای پخش روان‌تر
        '-f', 'hls', 
        '-hls_time', '2', 
        '-hls_list_size', '5',
        '-hls_flags', 'delete_segments', 
        'live.m3u8'
    ]
    
    print(f"⚙️ تنظیمات استریم: {width}x{height} | {fps} FPS | Bitrate: {bitrate}")
    print("🎥 راه‌اندازی مرورگر مخفی و موتور ویدیو...")

    ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    end_time = time.time() + (args.duration * 60)
    frame_delay = 1.0 / fps
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': width, 'height': height})
        page.goto(args.url)
        
        while time.time() < end_time:
            start_loop = time.time()
            try:
                # گرفتن اسکرین‌شات با فرمت JPEG برای سرعت بیشتر
                screenshot = page.screenshot(type='jpeg', quality=60)
                ffmpeg_proc.stdin.write(screenshot)
                ffmpeg_proc.stdin.flush()
            except Exception as e:
                break
                
            # کنترل دقیق زمان فریم‌ها برای جلوگیری از تند یا کند شدن ویدیو
            elapsed = time.time() - start_loop
            sleep_time = frame_delay - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        browser.close()
        ffmpeg_proc.stdin.close()
        ffmpeg_proc.wait()

if __name__ == "__main__":
    main()
