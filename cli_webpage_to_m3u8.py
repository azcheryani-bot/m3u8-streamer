import argparse
import os
import time
import threading
import subprocess
import glob
import boto3
from botocore.client import Config
from flask import Flask, make_response

app = Flask(__name__)

# فایل HTML شما با تمامی تنظیمات
HTML_CONTENT = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>نمایشگر زنده مراسم</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = { theme: { extend: { fontFamily: { sans: ['Vazirmatn', 'sans-serif'], } } } }
    </script>
    <link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@100;300;400;700;900&family=Lalezar&family=Noto+Nastaliq+Urdu:wght@400;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script src="https://cdn.socket.io/4.8.1/socket.io.min.js"></script>
    <style>
        body { font-family: 'Vazirmatn', sans-serif; margin: 0; padding: 0; overflow: hidden; -webkit-font-smoothing: antialiased; }
        @keyframes scrollSeamless { 0% { transform: translate3d(-50%, 0, 0); } 100% { transform: translate3d(0, 0, 0); } }
        .marquee-content { display: flex; width: max-content; will-change: transform; align-items: center; }
    </style>
</head>
<body class="bg-slate-950 text-slate-100">
    <div class="relative w-full h-screen overflow-hidden bg-slate-950 font-sans select-none" dir="ltr">
        <div id="bgImage" class="absolute inset-0 bg-cover bg-center z-0 transition-all duration-1000 opacity-60"></div>
        <div class="absolute inset-0 bg-gradient-to-b from-slate-900 via-slate-900/50 to-slate-900 z-0"></div>
        <div class="relative z-10 flex flex-col h-full" dir="rtl">
            <div class="flex-shrink-0 flex items-center justify-between px-4 md:px-12 py-4 h-[25vh] md:h-[28vh] border-b border-white/5 bg-black/20 backdrop-blur-sm">
                <div class="flex flex-col justify-center h-full max-w-[70%]">
                    <h1 id="eventTitle" class="font-black drop-shadow-[0_4px_4px_rgba(0,0,0,0.8)] border-r-8 border-yellow-500 pr-6 transition-all duration-300 break-words leading-tight" style="color: #ffffff; font-size: 3.5rem;">
                        در حال بارگذاری...
                    </h1>
                </div>
                <div id="deceasedContainer" class="h-full py-2 flex items-center hidden">
                    <div class="h-[90%] aspect-[3/4] relative rounded-2xl overflow-hidden shadow-[0_0_30px_rgba(234,179,8,0.3)] ring-4 ring-yellow-500/80 bg-slate-800">
                       <img id="deceasedImage" src="" class="w-full h-full object-cover" alt="Deceased" />
                       <div class="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black via-black/70 to-transparent pt-8 pb-2 text-center">
                          <span id="deceasedLabel" class="font-bold drop-shadow-md"></span>
                       </div>
                    </div>
                </div>
            </div>
            <div class="flex-grow flex flex-col w-full min-h-0 bg-black/10">
                <div data-base-class="h-[38%] w-full relative overflow-hidden flex items-center" class="h-[38%] w-full relative overflow-hidden flex items-center" dir="ltr"><div id="highMarquee" class="marquee-content"></div></div>
                <div data-base-class="h-[32%] w-full relative overflow-hidden flex items-center" class="h-[32%] w-full relative overflow-hidden flex items-center" dir="ltr"><div id="midMarquee" class="marquee-content"></div></div>
                <div data-base-class="h-[30%] w-full relative overflow-hidden flex items-center" class="h-[30%] w-full relative overflow-hidden flex items-center" dir="ltr"><div id="lowMarquee" class="marquee-content"></div></div>
            </div>
            <div class="flex-shrink-0 h-[7vh] flex items-center justify-center bg-black/80 backdrop-blur-md border-t border-white/10">
                <p id="footerText" class="font-bold animate-pulse text-center px-4 drop-shadow-lg text-lg"></p>
            </div>
        </div>
    </div>
    <div id="announcementOverlay" class="fixed inset-0 bg-black z-[9999] flex items-center justify-center hidden">
        <img id="announcementImg" src="" class="max-w-full max-h-full object-contain" alt="Announcement" />
    </div>
    <script>
        const DEFAULT_SETTINGS = { fontSize: 40, scrollSpeed: 20, highThreshold: 5000000, midThreshold: 1000000, fontHigh: 'Vazirmatn', fontMid: 'Vazirmatn', fontLow: 'Vazirmatn', showAnnouncement: false, eventTitle: 'مراسم ترحیم', titleColor: '#ffffff', titleSize: 3.5, deceasedLabel: 'شادروان', deceasedLabelColor: '#fef3c7', deceasedLabelSize: 12, footerText: 'شادی روح درگذشتگان صلوات', footerColor: '#ffffff', footerSize: 14, };
        let currentSettings = { ...DEFAULT_SETTINGS };
        let currentDonations = [];
        let activeEventId = 'active';
        const BASE_URL = 'https://kheyriyeh3.hudsonparker87.workers.dev';

        async function fetchJSON(endpoint) {
            try { const url = BASE_URL + endpoint; const res = await fetch(url + (url.includes('?') ? '&' : '?') + '_t=' + Date.now()); if (!res.ok) return null; return await res.json(); } catch (e) { return null; }
        }

        async function updateData() {
            const [eventData, configData] = await Promise.all([ fetchJSON('/api/db/events/active'), fetchJSON('/api/db/config/displaySettings') ]);
            if (eventData && eventData.id) activeEventId = eventData.id;
            const configVal = (configData && configData.value) ? configData.value : {};
            const effectiveTitle = (eventData && eventData.title) ? eventData.title : (configVal.eventTitle || DEFAULT_SETTINGS.eventTitle);
            currentSettings = { ...DEFAULT_SETTINGS, ...configVal, eventTitle: effectiveTitle };
            const donations = await fetchJSON(`/api/db/donations/${activeEventId}/approved`);
            if (donations && Array.isArray(donations)) { currentDonations = donations; }
            render();
        }

        function createMarqueeItem(item, fontSize, font) {
            const div = document.createElement('div');
            div.className = "flex flex-col items-center justify-center px-6 md:px-10 mx-2 py-2 rounded-2xl border border-white/10 bg-white/5 backdrop-blur-md shadow-xl flex-shrink-0";
            div.style.fontFamily = font; div.style.minWidth = 'fit-content';
            const nameSpan = document.createElement('span');
            nameSpan.className = "font-bold whitespace-nowrap drop-shadow-lg text-yellow-50";
            nameSpan.style.fontSize = `${fontSize}px`; nameSpan.style.lineHeight = '1.4'; nameSpan.textContent = item.donorName;
            div.appendChild(nameSpan);
            if (item.fatherName) {
                const fatherSpan = document.createElement('span');
                fatherSpan.className = "text-white/90 font-light mt-0.5 whitespace-nowrap tracking-wide";
                fatherSpan.style.fontSize = `${fontSize * 0.55}px`; fatherSpan.textContent = `(${item.fatherName})`;
                div.appendChild(fatherSpan);
            }
            return div;
        }

        function renderMarqueeRow(containerId, list, speed, fontSize, font, bgClasses, emptyClasses) {
            const wrapper = document.getElementById(containerId).parentElement;
            const container = document.getElementById(containerId);
            container.innerHTML = '';
            if (!list || list.length === 0) {
                const empty = document.createElement('div'); empty.className = "w-full flex items-center justify-center h-full";
                empty.innerHTML = `<span class="text-white/20 text-lg font-bold italic animate-pulse">...</span>`;
                wrapper.className = wrapper.dataset.baseClass + " " + emptyClasses;
                container.style.animation = 'none'; container.className = "w-full h-full"; container.appendChild(empty);
                return;
            }
            wrapper.className = wrapper.dataset.baseClass + " " + bgClasses;
            container.className = "flex w-max will-change-transform items-center";
            let items = [...list]; const MIN_ITEMS = 40;
            while (items.length < MIN_ITEMS) { items = [...items, ...list]; }
            const renderList = [...items, ...items];
            const duration = (renderList.length * 120) / (speed || 20);
            renderList.forEach(item => { container.appendChild(createMarqueeItem(item, fontSize, font)); });
            container.style.animation = `scrollSeamless ${duration}s linear infinite`;
        }

        function render() {
            const isMobile = window.innerWidth < 768; const fontScale = isMobile ? 0.5 : 1; const baseFontSize = currentSettings.fontSize * fontScale;
            const overlay = document.getElementById('announcementOverlay');
            if (currentSettings.showAnnouncement && currentSettings.announcementImage) {
                overlay.classList.remove('hidden'); document.getElementById('announcementImg').src = currentSettings.announcementImage; return;
            } else { overlay.classList.add('hidden'); }
            const bgImage = document.getElementById('bgImage');
            if (currentSettings.bgImage) { bgImage.style.backgroundImage = `url(${currentSettings.bgImage})`; } else { bgImage.style.backgroundImage = 'none'; }
            const titleEl = document.getElementById('eventTitle');
            titleEl.textContent = currentSettings.eventTitle; titleEl.style.color = currentSettings.titleColor; titleEl.style.fontSize = `${isMobile ? Math.max(1.5, currentSettings.titleSize * 0.6) : currentSettings.titleSize}rem`;
            const deceasedContainer = document.getElementById('deceasedContainer');
            if (currentSettings.deceasedImage) {
                deceasedContainer.classList.remove('hidden'); document.getElementById('deceasedImage').src = currentSettings.deceasedImage;
                const label = document.getElementById('deceasedLabel'); label.textContent = currentSettings.deceasedLabel; label.style.color = currentSettings.deceasedLabelColor; label.style.fontSize = `${isMobile ? 12 : currentSettings.deceasedLabelSize}px`;
            } else { deceasedContainer.classList.add('hidden'); }
            if (currentSettings.customFontData && typeof FontFace !== 'undefined') {
                const fontFace = new FontFace('CustomUploaded', `url(${currentSettings.customFontData})`);
                fontFace.load().then(loadedFace => { if (document.fonts) document.fonts.add(loadedFace); }).catch(e => console.error("Font load error:", e));
            }
            const footerEl = document.getElementById('footerText');
            footerEl.textContent = currentSettings.footerText; footerEl.style.color = currentSettings.footerColor; footerEl.style.fontSize = `${isMobile ? currentSettings.footerSize * 0.8 : currentSettings.footerSize}px`;
            const visibleDonations = currentDonations.filter(d => !d.hideName);
            const high = visibleDonations.filter(d => d.amount >= currentSettings.highThreshold);
            const mid = visibleDonations.filter(d => d.amount < currentSettings.highThreshold && d.amount >= currentSettings.midThreshold);
            const low = visibleDonations.filter(d => d.amount < currentSettings.midThreshold);
            renderMarqueeRow('highMarquee', high, currentSettings.scrollSpeed * 0.7, baseFontSize * 1.6, currentSettings.fontHigh, "bg-gradient-to-r from-yellow-900/30 via-yellow-900/10 to-yellow-900/30 border-yellow-500/20 border-b border-white/10 backdrop-blur-sm shadow-lg", "border-b border-white/5 bg-black/10 backdrop-blur-sm");
            renderMarqueeRow('midMarquee', mid, currentSettings.scrollSpeed, baseFontSize * 1.2, currentSettings.fontMid, "bg-gradient-to-r from-blue-900/30 via-blue-900/10 to-blue-900/30 border-blue-500/20 border-b border-white/10 backdrop-blur-sm shadow-lg", "border-b border-white/5 bg-black/10 backdrop-blur-sm");
            renderMarqueeRow('lowMarquee', low, currentSettings.scrollSpeed * 1.2, baseFontSize * 0.9, currentSettings.fontLow, "bg-gradient-to-r from-slate-900/40 via-slate-800/20 to-slate-900/40 border-white/5 border-b border-white/10 backdrop-blur-sm shadow-lg", "border-b border-white/5 bg-black/10 backdrop-blur-sm");
        }
        updateData(); setInterval(updateData, 30000); 
        if (typeof io !== 'undefined') { const socket = io(BASE_URL, { path: '/socket.io', transports: ['websocket', 'polling'] }); socket.on('db_change', () => { updateData(); }); }
        window.addEventListener('resize', render);
    </script>
</body>
</html>"""

@app.route('/')
def serve_index():
    response = make_response(HTML_CONTENT)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response

# مشخصات استوریج نئون شما
S3_ENDPOINT = "https://br-lucky-wave-axbfuzrm.storage.c-4.us-east-2.aws.neon.tech"
S3_ACCESS_KEY = "nak_live_1bfd6791115643c59cee64e82e36e1cd"
S3_SECRET_KEY = "nsk_live_a15238f9642107cd7482831f8d003dfbf6d2bdcae52bb44b099eb321a74c60a7"
S3_REGION = "us-east-2"
BUCKET_NAME = "m3u8-streamer"

s3_client = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    region_name=S3_REGION,
    config=Config(signature_version='s3v4')
)

def run_server():
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host='127.0.0.1', port=8080)

# ربات آپلود خودکار و بلادرنگ به نئون
def s3_sync_worker(stop_event):
    uploaded_files = set()
    print("☁️ همگام‌ساز خودکار به حافظه ابری نئون فعال شد.")
    while not stop_event.is_set():
        # آپلود فایل‌های تکه ویدیویی (.ts)
        for ts_file in glob.glob("*.ts"):
            if ts_file not in uploaded_files and os.path.exists(ts_file):
                try:
                    s3_client.upload_file(
                        ts_file, BUCKET_NAME, ts_file,
                        ExtraArgs={'ContentType': 'video/MP2T', 'CacheControl': 'public, max-age=3600'}
                    )
                    uploaded_files.add(ts_file)
                except Exception as e:
                    pass
        
        # آپلود فایل پلی‌لیست (.m3u8) به محض تغییر
        if os.path.exists("live.m3u8"):
            try:
                s3_client.upload_file(
                    "live.m3u8", BUCKET_NAME, "live.m3u8",
                    ExtraArgs={'ContentType': 'application/vnd.apple.mpegurl', 'CacheControl': 'no-cache, no-store, must-revalidate'}
                )
            except Exception as e:
                pass

        time.sleep(0.5)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--quality', required=True)
    parser.add_argument('--fps', required=True, type=int)
    parser.add_argument('--duration', required=True, type=int)
    args = parser.parse_args()

    qualities = {
        '240p': ('426x240', '500k'),
        '360p': ('640x360', '800k'),
        '480p': ('854x480', '1200k'),
        '720p': ('1280x720', '2500k'),
        '1080p': ('1920x1080', '4500k'),
    }
    resolution, bitrate = qualities.get(args.quality, qualities['720p'])
    fps = args.fps

    for f in glob.glob("*.ts") + glob.glob("*.m3u8"):
        try: os.remove(f)
        except: pass

    # 1. سرور صفحه نمایشگر داخلی
    threading.Thread(target=run_server, daemon=True).start()
    time.sleep(1)

    # 2. مانیتور مجازی
    os.environ["DISPLAY"] = ":99"
    subprocess.Popen(['Xvfb', ':99', '-screen', '0', f'{resolution}x24', '-ac'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)

    # 3. باز کردن تمام صفحه HTML روی مانیتور مجازی
    chrome_cmd = [
        'chromium-browser', '--kiosk', '--no-sandbox', '--disable-infobars',
        '--disable-dev-shm-usage', f'--window-size={resolution.replace("x", ",")}',
        'http://127.0.0.1:8080/'
    ]
    subprocess.Popen(chrome_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)

    # 4. شروع استریم ویدیویی
    ffmpeg_cmd = [
        'ffmpeg', '-y', '-f', 'x11grab', '-video_size', resolution,
        '-framerate', str(fps), '-i', ':99.0', '-c:v', 'libx264',
        '-preset', 'ultrafast', '-tune', 'zerolatency',
        '-b:v', bitrate, '-maxrate', bitrate,
        '-bufsize', str(int(bitrate.replace('k',''))*2) + 'k',
        '-pix_fmt', 'yuv420p', '-g', str(fps * 2),
        '-f', 'hls', '-hls_time', '2', '-hls_list_size', '5',
        '-hls_flags', 'delete_segments', 'live.m3u8'
    ]
    ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 5. روشن کردن آپلودر به سرور ابری نئون
    stop_event = threading.Event()
    uploader_thread = threading.Thread(target=s3_sync_worker, args=(stop_event,), daemon=True)
    uploader_thread.start()

    # چاپ لینک ثابت و ابدی استریم شما
    neon_stream_url = f"{S3_ENDPOINT}/{BUCKET_NAME}/live.m3u8"
    print("\n" + "="*60)
    print("🚀 پخش زنده با موفقیت روی سرور اختصاصی ابری نئون آغاز شد!")
    print(f"🔗 آدرس استریم ثابت و دائمی شما:")
    print(f"👉 {neon_stream_url}")
    print("="*60 + "\n")

    time.sleep(args.duration * 60)
    stop_event.set()
    ffmpeg_proc.terminate()
    print("✅ زمان استریم به پایان رسید.")

if __name__ == "__main__":
    main()
