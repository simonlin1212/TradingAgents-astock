#!/bin/bash
# TradingAgents-Astock CLI 快速启动
# 用法: ./start_cli.sh [股票代码] [日期]
# 例如: ./start_cli.sh 300750 2026-05-26

cd ~/A1WorkSpace/TradingAgents-astock

# 加载环境变量
export $(grep -v '^#' .env | xargs)
export $(grep -v '^#' ~/.hermes/.env | xargs 2>/dev/null)

# 检查并配置 mootdx TDX 服务器（用于中文股票名解析）
python3 -c "
import json, os, subprocess, sys
config_path = os.path.expanduser('~/.mootdx/config.json')
need_bestip = True
if os.path.exists(config_path):
    try:
        with open(config_path) as f:
            cfg = json.load(f)
        servers = cfg.get('servers', [])
        if servers and any(s.get('host') and s.get('port') for s in servers):
            need_bestip = False
    except Exception:
        pass
if need_bestip:
    subprocess.run([sys.executable, '-m', 'mootdx', 'bestip'], capture_output=True, text=True, timeout=60)
" 2>&1 | grep -v "^2026"

if [ -n "$1" ]; then
    # 如果提供了参数，直接分析
    python3 -c "
from tradingagents.model_profile import get_active_config
from tradingagents.graph.trading_graph import TradingAgentsGraph

config = get_active_config()
print(f'Provider: {config[\"llm_provider\"]}')
print(f'Quick model: {config[\"quick_think_llm\"]}')
print(f'Deep model: {config[\"deep_think_llm\"]}')
print(f'Analyzing: $1 on ${2:-$(date +%Y-%m-%d)}')
print('---')

ta = TradingAgentsGraph(debug=True, config=config)
final_state, decision = ta.propagate('$1', '${2:-$(date +%Y-%m-%d)}')
print(decision)
"
else
    # 进入交互模式
    tradingagents
fi
