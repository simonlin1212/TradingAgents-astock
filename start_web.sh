#!/bin/bash
# TradingAgents-Astock Web UI 启动脚本
# 双击桌面图标即可启动

cd ~/A1WorkSpace/TradingAgents-astock

# 加载环境变量
export $(grep -v '^#' .env | xargs)
export $(grep -v '^#' ~/.hermes/.env | xargs 2>/dev/null)

# 检查并配置 mootdx TDX 服务器（用于中文股票名解析）
echo "🔧 检查 mootdx 服务器配置..."
python3 -c "
import json, os, subprocess, sys

config_path = os.path.expanduser('~/.mootdx/config.json')

# 检查是否已有有效配置
need_bestip = True
if os.path.exists(config_path):
    try:
        with open(config_path) as f:
            cfg = json.load(f)
        servers = cfg.get('servers', [])
        if servers and any(s.get('host') and s.get('port') for s in servers):
            need_bestip = False
            print('  ✓ mootdx 服务器已配置，跳过')
    except Exception:
        pass

if need_bestip:
    print('  → 正在搜索最快 TDX 服务器...')
    result = subprocess.run(
        [sys.executable, '-m', 'mootdx', 'bestip'],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode == 0:
        print('  ✓ mootdx 服务器配置完成')
    else:
        print('  ⚠ mootdx 服务器配置失败（中文股票名解析可能不可用）')
        print('    可手动运行: python3 -m mootdx bestip')
" 2>&1 | grep -v "^2026\|^$"

echo ""
echo "🚀 启动 TradingAgents Web UI..."
echo "   访问地址: http://localhost:8501"
echo ""

# 启动 Streamlit Web UI（后台运行，不阻塞浏览器打开）
streamlit run web/app.py --server.port 8501 --server.headless true &
STREAMLIT_PID=$!

# 等待 Streamlit 就绪后自动打开浏览器
echo "⏳ 等待 Streamlit 启动..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8501 > /dev/null 2>&1; then
        echo "✅ Streamlit 已启动，正在打开浏览器..."
        open http://localhost:8501
        break
    fi
    sleep 1
done

# 等待 Streamlit 进程结束（保持 Terminal 窗口打开）
wait $STREAMLIT_PID
