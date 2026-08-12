import sys
import os
import time
import re
import tempfile
import shutil
import subprocess
import threading
import argparse
import requests
from flask import Flask, send_from_directory
import imageio_ffmpeg
from playwright.sync_api import sync_playwright

QUALITY_PRESETS = {
    "240p": {"width": 426, "height": 240, "fps": 5, "bitrate": "300k", "preset": "ultrafast"},
    "360p": {"width": 640, "height": 360, "fps": 10, "bitrate": "600k", "preset": "ultrafast"},
    "480p": {"width": 854, "height": 480, "fps": 15, "bitrate": "1200k", "preset": "ultrafast"},
    "720p": {"width": 1280, "height": 720, "fps": 20, "bitrate": "2500k", "preset": "superfast"},
    "1080p": {"width": 1920, "height": 1080, "fps": 30, "bitrate": "5000k", "preset": "veryfast"},
    "1440p": {"width": 2560, "height": 1440, "fps": 60, "bitrate": "9000k", "preset": "faster"}
}

TEMP_DIR = os.path.join(tempfile.gettempdir(), "github_m3u8_stream")
app = Flask(__name__)

@app.route('/<path:filename>')
def serve_stream_files(filename):
    """ارائه فایل‌های M3U8 و قطعات TS به صورت HTTP"""
    response = send_from_directory(TEMP_DIR, filename)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

def start_ssh_tunnel(port):
    """ایجاد تونل عمومی SSH برای دسترسی اینترنتی به لینک استریم"""
    print("🌐 در حال برقراری اتصال به تونل عمومی SSH (localhost.run)...")
    cmd = [
        "ssh", "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=30",
        "-R", f"80:localhost:{port}",
        "nokey@localhost.run"
    ]
    
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        start_time = time.time()
        public_url = None
        
        while time.time() - start_time < 30:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            
            matches = re.findall(r'https://[a-zA-Z0-9-]+\.lhr\.life', line)
            if matches:
                found_url = matches[0]
                if "admin.localhost.run" not in found_url:
                    public_url = found_url
                    break
                    
        if public_url:
            print("\n" + "="*60)
            print(f"🚀 لینک عمومی استریم M3U8 آماده شد:")
            print(f"🔗 {public_url}/live.m3u8")
            print("="*60 + "\n")
            return proc, public_url
        else:
            print("⚠️ نتوانستیم لینک عمومی SSH را در زمان تعیین شده استخراج کنیم.")
            return proc, None
    except Exception as e:
        print(f"❌ خطای تونل SSH: {e}")
        return None, None

def capture_and_stream(url, quality_key, duration_minutes):
    """ضبط زنده صفحه وب و تبدیل به فایل M3U8"""
    config = QUALITY_PRESETS.get(quality_key, QUALITY_PRESETS["720p"])
    width = config["width"]
    height = config["height"]
    fps = config["fps"]
    bitrate = config["bitrate"]
    preset = config["preset"]

    print(f"⚙️ تنظیمات استریم: کیفیت {quality_key} ({width}x{height} | {fps} FPS | Bitrate: {bitrate})")
    
    if os.path.exists(TEMP_DIR):
        try:
            shutil.rmtree(TEMP_DIR)
        except Exception:
            pass
    os.makedirs(TEMP_DIR, exist_ok=True)

    m3u8_file_path = os.path.join(TEMP_DIR, "live.m3u8")
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    ffmpeg_cmd = [
        ffmpeg_exe, "-y",
        "-f", "image2pipe",
        "-vcodec", "png",
        "-r", str(fps),
        "-i", "-",
        "-c:v", "libx264",
        "-b:v", bitrate,
        "-preset", preset,
        "-tune", "zerolatency",
        "-pix_fmt", "yuv420p",
        "-g", str(fps * 2),
        "-hls_time", "2",
        "-hls_list_size", "5",
        "-hls_flags", "delete_segments+omit_endlist",
        "-f", "hls",
        m3u8_file_path
    ]

    print("🎥 راه‌اندازی موتور پردازش ویدیو FFmpeg...")
    ffmpeg_proc = subprocess.Popen(
        ffmpeg_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    port = 8080
    server_thread = threading.Thread(
        target=lambda: app.run(host='0.0.0.0', port=port, threaded=True, use_reloader=False),
        daemon=True
    )
    server_thread.start()
    print(f"📡 سرور محلی روی پورت {port} روشن شد.")

    tunnel_proc, public_url = start_ssh_tunnel(port)

    print(f"🌐 باز کردن مرورگر مخفی و بارگذاری وب‌سایت: {url}")
    end_time = time.time() + (duration_minutes * 60)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()
            
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            print("✅ صفحه وب بارگذاری شد. شروع فرایند ساخت استریم زنده...")

            frame_interval = 1.0 / fps

            while time.time() < end_time:
                start_loop = time.time()
                try:
                    screenshot_bytes = page.screenshot(type="png")
                    if ffmpeg_proc.poll() is not None:
                        break
                    ffmpeg_proc.stdin.write(screenshot_bytes)
                    ffmpeg_proc.stdin.flush()
                except Exception as capture_err:
                    print(f"⚠️ خطای ضبط فریم: {capture_err}")
                    break

                elapsed = time.time() - start_loop
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

            print("⏰ زمان اجرای تعیین شده به پایان رسید.")
            browser.close()
    except Exception as e:
        print(f"❌ خطای مرورگر: {e}")
    finally:
        if ffmpeg_proc and ffmpeg_proc.poll() is None:
            try:
                ffmpeg_proc.stdin.close()
                ffmpeg_proc.wait(timeout=3)
            except Exception:
                ffmpeg_proc.kill()
        if tunnel_proc:
            try:
                tunnel_proc.kill()
            except Exception:
                pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Webpage to Live M3U8 Streamer for Cloud / GitHub Actions")
    parser.add_argument("--url", type=str, required=True, help="آدرس کامل صفحه وب")
    parser.add_argument("--quality", type=str, default="720p", choices=list(QUALITY_PRESETS.keys()), help="کیفیت ویدیوی خروجی")
    parser.add_argument("--duration", type=int, default=60, help="مدت زمان اجرا به دقیقه")

    args = parser.parse_args()
    
    print("="*60)
    print("🚀 شروع اجرای استریم در محیط بدون رابط گرافیکی (CLI)")
    print(f"🔗 آدرس: {args.url}")
    print(f"📺 کیفیت: {args.quality}")
    print(f"⏱️ مدت اجرا: {args.duration} دقیقه")
    print("="*60)

    capture_and_stream(args.url, args.quality, args.duration)
