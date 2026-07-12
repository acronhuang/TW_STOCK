#!/usr/bin/env python3
"""
取得 LINE User ID 的工具
========================
啟動後會在 localhost:8765 開一個 webhook server。

步驟：
1. 執行此腳本
2. 到 LINE Developers Console → 你的 Channel → Messaging API
3. 設定 Webhook URL 為 ngrok 或其他公開 URL（或用 LINE Bot 測試工具）
4. 用 LINE 傳任何訊息給你的 Bot
5. 腳本會印出你的 User ID

替代方式（不需 webhook）：
- 到 LINE Developers Console → 你的 Channel → Basic settings
- 在「Your user ID」欄位直接看到
"""

import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv

load_dotenv()

class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length)
        data = json.loads(body)

        print('\n=== 收到 LINE Webhook ===')
        print(json.dumps(data, indent=2, ensure_ascii=False))

        # 提取 User ID
        for event in data.get('events', []):
            user_id = event.get('source', {}).get('userId', '')
            if user_id:
                print(f'\n{"="*50}')
                print(f'  你的 LINE User ID: {user_id}')
                print(f'{"="*50}')
                print(f'\n  請將此 ID 加入 .env:')
                print(f'  LINE_USER_ID={user_id}')

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'LINE Webhook Server Running')

    def log_message(self, format, *args):
        pass  # 靜音 HTTP log

if __name__ == '__main__':
    print('='*50)
    print('  LINE User ID 取得工具')
    print('='*50)
    print()
    print('  方法一（最簡單）：')
    print('  到 LINE Developers Console → 你的 Channel')
    print('  → Basic settings → 「Your user ID」')
    print()
    print('  方法二（Webhook）：')
    print('  Webhook server 啟動於 http://localhost:8765')
    print('  設定 Webhook URL 後，傳訊息給 Bot 即可取得 User ID')
    print()
    print('  按 Ctrl+C 結束')
    print('='*50)

    server = HTTPServer(('0.0.0.0', 8765), WebhookHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止')
