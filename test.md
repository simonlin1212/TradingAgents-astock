# 测试语句库

## K线数据测试
```bash
python -c "from tradingagents.dataflows.a_stock import get_stock_data; print(get_stock_data('600519', '2026-05-01', '2026-05-16'))"
```
这段代码是用来测试能否正常获取K线数据的，使用方法是直接在根目录所在的终端执行。如果正常运行应该能显示若干条股票数据

## 技术指标测试
```bash
python -c "from tradingagents.dataflows.a_stock import get_indicators; print(get_indicators('600519', 'rsi', '2026-05-16', 30))"
```
使用方法同上

## 启动 Streamlit
```bash
streamlit run web/app.py
```

## 安装依赖
```bash
pip install -r requirements.txt
```

## Git 常用
```bash
git status 
git add .
git add web/app.py
git commit 
git commit -m "message"
git checkout main
git pull upstream main
git push origin main
```