<p align="center"><a href="README.md">简体中文</a> | <a href="README_en.md">English</a> | <b>日本語</b></p>

<h1 align="center">TradingAgents-Astock</h1>

<p align="center">
  <a href="https://github.com/TauricResearch/TradingAgents">TauricResearch/TradingAgents</a>（65K ⭐）を中国 A 株向けに深く特化させたフォークです<br>
  完全な Apache 2.0 オープンソース · <code>pip install</code> ですぐに実行 · 外部サービスへの依存ゼロ
</p>

<p align="center">
  <b>⚠️ 本プロジェクトは <a href="https://arxiv.org/abs/2412.20138">TradingAgents 論文</a>のエンジニアリング実装および研究上の再現であり、研究・教育目的での利用を想定しています。<br>
  投資助言には当たらず、いかなる投資サービスも提供しません。</b>
</p>

<p align="center">
  <a href="https://github.com/simonlin1212/tradingagents-astock/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/simonlin1212/tradingagents-astock?style=social"/></a>
  <a href="https://github.com/simonlin1212/tradingagents-astock/network/members"><img alt="Forks" src="https://img.shields.io/github/forks/simonlin1212/tradingagents-astock?style=social"/></a>
  <a href="https://arxiv.org/abs/2412.20138"><img alt="Paper" src="https://img.shields.io/badge/paper-arXiv_2412.20138-B31B1B?logo=arxiv"/></a>
  <a href="./LICENSE"><img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-blue"/></a>
  <a href="./CHANGES_FROM_UPSTREAM.md"><img alt="Changes" src="https://img.shields.io/badge/changes-CHANGES-orange"/></a>
</p>

<p align="center">
  <a href="#このフォークを作った理由">このフォークを作った理由</a> ·
  <a href="#アップストリームとの比較">比較</a> ·
  <a href="#アーキテクチャの概要">アーキテクチャ</a> ·
  <a href="#7-つのアナリストロール">アナリストロール</a> ·
  <a href="#データソース">データソース</a> ·
  <a href="#クイックスタート">クイックスタート</a> ·
  <a href="#web-ui">Web UI</a> ·
  <a href="#よくあるトラブルシューティング">トラブルシューティング</a>
</p>

---


## このフォークを作った理由

オリジナルの TradingAgents は優れたマルチエージェント研究フレームワークですが、米国株式市場向けに設計されています。データは Yahoo Finance / Alpha Vantage から取得され、アナリストは A 株の制度を理解しておらず、議論も意思決定も完全に米国市場向けです。

**このフォークの目標**：TradingAgents のマルチエージェントによるディベート型アーキテクチャを、本当の意味で A 株市場に適応させることです。単なる翻訳ではなく、データレイヤー、エージェントの役割、取引ルールという 3 つの側面にわたる深い特化です。

### 主な変更点

<table>
<thead>
<tr><th nowrap>側面</th><th>オリジナル</th><th>このフォーク</th></tr>
</thead>
<tbody>
<tr><td nowrap><strong>データソース</strong></td><td>Yahoo Finance / Alpha Vantage</td><td>mootdx + 東方財富（Eastmoney）+ 新浪（Sina）+ 同花順（Tonghuashun）（すべて無料の直接接続）</td></tr>
<tr><td nowrap><strong>アナリストの役割</strong></td><td>4 つ（マーケット / センチメント / ニュース / ファンダメンタルズ）</td><td><strong>7 つ</strong>（+ 政策アナリスト / 仕手筋トラッカー / ロックアップ解除モニター）</td></tr>
<tr><td nowrap><strong>取引ルール</strong></td><td>米国市場（T+0、値幅制限なし）</td><td>A 株市場（T+1、値幅制限、最低売買単位、取引時間）</td></tr>
<tr><td nowrap><strong>出力言語</strong></td><td>英語</td><td>中国語のレポート（推論の質を保つため、内部のディベートは英語のまま）</td></tr>
<tr><td nowrap><strong>アルファのベンチマーク</strong></td><td>SPY</td><td>CSI 300（沪深300）</td></tr>
</tbody>
</table>

---
## アップストリームとの比較

| 機能 | オリジナルの TradingAgents | **このフォーク** |
|---------|------------------------|---------------|
| ライセンス | Apache 2.0 | **完全な Apache 2.0** |
| デプロイの依存関係 | pip install | **すぐに使える** |
| A 株データ | ❌ | **mootdx + 東方財富 + 新浪 + 同花順（直接 HTTP）** |
| A 株に特化した役割 | ❌ | **3 つの専門ロール：政策 / 仕手筋 / ロックアップ解除** |
| A 株の取引制約 | ❌ | **完全対応：T+1 / 値幅制限 / 売買単位 / ST** |
## アーキテクチャの概要

```
┌─────────────────────────────────────────────────────────┐
│                    7 Analyst Research Report Generation  │
│  Market → Social → News → Fundamentals                   │
│  → Policy → Hot Money → Lockup                           │
│         (Each Analyst has tool loop)                     │
├─────────────────────────────────────────────────────────┤
│               Bull vs Bear Investment Research Debate    │
│         Bull Researcher ←→ Bear Researcher               │
│               (Up to N rounds of debate)                 │
├─────────────────────────────────────────────────────────┤
│              Research Manager Comprehensive Assessment   │
│         (Deep thinking LLM, outputs investment plan)    │
├─────────────────────────────────────────────────────────┤
│                  Trader Trading Plan                     │
│         (A-share constraints: T+1/price limit/lot size) │
├─────────────────────────────────────────────────────────┤
│        Aggressive ←→ Conservative ←→ Neutral             │
│               Three-way Risk Debate                      │
├─────────────────────────────────────────────────────────┤
│            Portfolio Manager Final Decision              │
│     (Deep thinking LLM, outputs rating + rationale)     │
└─────────────────────────────────────────────────────────┘
```

**デュアル LLM 設計**：
- `quick_think_llm`：すべてのアナリスト、リサーチャー、トレーダー、リスクディベーター
- `deep_think_llm`：リサーチマネージャーとポートフォリオマネージャー（意思決定に全体の情報を総合的に把握する必要があるため）

---
## 7 つのアナリストロール

### オリジナルの 4 ロール（A 株向けに適応）

<table>
<thead>
<tr><th nowrap>ロール</th><th>担当</th><th>データツール</th></tr>
</thead>
<tbody>
<tr><td nowrap>🏪 マーケットアナリスト</td><td>ローソク足のパターン、テクニカル指標、出来高と価格の分析</td><td><code>get_stock_data</code>, <code>get_indicators</code></td></tr>
<tr><td nowrap>💬 センチメントアナリスト</td><td>ソーシャルメディアのセンチメント、個人投資家の議論の盛り上がり</td><td><code>get_news</code></td></tr>
<tr><td nowrap>📰 ニュースアナリスト</td><td>業界ニュース、適時開示、マクロイベント</td><td><code>get_news</code>, <code>get_global_news</code>, <code>get_insider_transactions</code></td></tr>
<tr><td nowrap>📊 ファンダメンタルズアナリスト</td><td>財務三表、収益性、バリュエーション</td><td><code>get_fundamentals</code>, <code>get_balance_sheet</code>, <code>get_cashflow</code>, <code>get_income_statement</code></td></tr>
</tbody>
</table>

### A 株固有の 3 ロール（新規）

<table>
<thead>
<tr><th nowrap>ロール</th><th>担当</th><th>データツール</th><th>必要な理由</th></tr>
</thead>
<tbody>
<tr><td nowrap>🏛️ 政策アナリスト</td><td>規制政策、産業政策、窓口指導</td><td><code>get_news</code>, <code>get_global_news</code></td><td>A 株は政策主導の市場であり、政策の変化がセクターローテーションに直接影響します</td></tr>
<tr><td nowrap>🔥 仕手筋トラッカー</td><td>龍虎榜（Dragon-Tiger リスト）、大口注文のフロー、主力資金の動向</td><td><code>get_stock_data</code>, <code>get_news</code>, <code>get_insider_transactions</code></td><td>仕手筋（ホットマネー）は、A 株の短期的な価格形成を左右する中心的な力です</td></tr>
<tr><td nowrap>🔓 ロックアップ解除モニター</td><td>制限株式のロックアップ解除、大株主による売却、株式担保</td><td><code>get_insider_transactions</code>, <code>get_news</code>, <code>get_fundamentals</code></td><td>ロックアップ解除は、A 株に特有の大きな供給ショック要因です</td></tr>
</tbody>
</table>

7 人のアナリストのレポートは、その後の強気/弱気ディベートと三者によるリスクディベートに取り込まれ、A 株固有の要因が意思決定の流れ全体に組み込まれるようにします。
## データソース

すべて無料で、API キー不要、ポイント制の制限もありません：

<table>
<thead>
<tr><th nowrap>ソース</th><th nowrap>プロトコル</th><th>提供される内容</th></tr>
</thead>
<tbody>
<tr><td nowrap><strong>mootdx</strong></td><td nowrap>TCP 7709</td><td>OHLCV のローソク足、財務スナップショット、F10 テキスト</td></tr>
<tr><td nowrap><strong>騰訊財経（Tencent Finance）</strong></td><td nowrap>HTTP（<code>qt.gtimg.cn</code>）</td><td>PER / PBR / 時価総額 / 売買回転率（リアルタイム）</td></tr>
<tr><td nowrap><strong>東方財富（East Money）</strong></td><td nowrap>HTTP（datacenter / push2）</td><td>龍虎榜、制限株式のロックアップ解除、セクターの相場、個別銘柄の情報</td></tr>
<tr><td nowrap><strong>新浪財経（Sina Finance）</strong></td><td nowrap>HTTP</td><td>ローソク足の履歴、財務諸表（3 表）</td></tr>
<tr><td nowrap><strong>同花順（Tonghuashun）</strong></td><td nowrap>HTTP（10jqka）</td><td>EPS のコンセンサス予想</td></tr>
<tr><td nowrap><strong>財聯社（Cailianshe）</strong></td><td nowrap>HTTP（cls.cn）</td><td>グローバルな金融ニュース速報</td></tr>
<tr><td nowrap><strong>百度股市通（Baidu Stock Market）</strong></td><td nowrap>HTTP（finance.pae.baidu）</td><td>コンセプトセクターの分類、資金フロー</td></tr>
</tbody>
</table>

> Tushare（ポイント制の制限）、Alpha Vantage（海外 API）、Yahoo Finance（A 株非対応）には一切依存していません。

---

> **データソースの優先順位と東方財富のブロック対策（v0.2.11）**：相場 / ローソク足 / 時価総額 / 財務データを mootdx（通達信 TCP、IP ブロックなし）または騰訊から取得できる場合は、常にそちらを使います。東方財富は、そこでしか得られないデータ（龍虎榜 / ロックアップ解除 / 資金フロー / セクター / 個別銘柄のニュースなど）にのみ使います。東方財富へのリクエストはすべて、組み込みのスロットリング入口 `_em_get()` を経由します。直列のレート制限（デフォルトの間隔は 1 秒以上 + 0.1〜0.5 秒のランダムなジッター）と Keep-Alive セッションの再利用により、複数のエージェントでバッチ分析を実行しても、一時的な IP ブロックが発生しなくなりました（東方財富のリスク管理の実測：毎秒 5 リクエスト超 / 同時接続 10 以上 / 1 分間に 200 リクエスト以上でブロックが発生）。バッチ処理のシナリオでは、環境変数 `EM_MIN_INTERVAL=1.5~2` を設定するとさらに速度を落とせます。**レート制限の対象は東方財富のみで、mootdx / 騰訊 / 新浪 / 同花順 / 財聯社 / 百度は影響を受けません。**
## クイックスタート

### 1. 環境のセットアップ

```bash
# Python >= 3.10
git clone https://github.com/simonlin1212/tradingagents-astock.git
cd tradingagents-astock
pip install -e .

# (Optional) Google Gemini — there is no [google] extra; install it explicitly (see FAQ):
pip install --no-deps "langchain-google-genai>=4.0.0"
pip install "google-genai>=1.53.0" "httpx>=0.28.1"
```

> **インストール後すぐに使え、Docker は不要です。** インストールしたら、`streamlit run web/app.py`（Web UI）または `tradingagents`（CLI）をそのまま実行してください。下の「Web UI」と「CLI」のセクションをご覧ください。Docker はオプションのデプロイ方法の 1 つにすぎず、ローカルでの開発には必要ありません。

### 2. LLM の設定

> **デフォルトでは API キーによる従量課金です。** 1 回の分析には 30〜50 回の LLM 呼び出しが必要です。
>
> **例外（v0.4.0 で追加）：** `pip install -e ".[agentsdk]"` で `[agentsdk]` をインストールすると、一部またはすべてのノードを Claude Agent SDK 経由で**個人の Claude Pro/Max サブスクリプションの利用枠**で実行でき、API の請求は発生しません。詳しくは中国語版 README の「[用个人 Claude 订阅额度](README.md#用个人-claude-订阅额度可选v040-新增)」をご覧ください。

プロジェクトのルートに `.env` ファイルを作成し、選んだプロバイダーに応じて設定します：

```bash
# ── Option A: MiniMax (Recommended for direct China access, cost-effective) ──
MINIMAX_API_KEY=sk-xxx
# Apply at: https://platform.minimaxi.com/

# ── Option B: DeepSeek ─────────────────────────────────────────────────────
DEEPSEEK_API_KEY=sk-xxx
# Apply at: https://platform.deepseek.com/

# ── Option C: Zhipu GLM ────────────────────────────────────────────────────
ZHIPU_API_KEY=xxx
# Apply at: https://open.bigmodel.cn/

# ── Option D: Tongyi Qianwen Qwen ──────────────────────────────────────────
DASHSCOPE_API_KEY=sk-xxx
# Apply at: https://dashscope.console.aliyun.com/

# ── Option E: OpenAI ───────────────────────────────────────────────────────
OPENAI_API_KEY=sk-xxx

# ── Option F: Anthropic ────────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-xxx

# ── Option G: Kimi (Anthropic-compatible API) ───────────────────────────────
ANTHROPIC_API_KEY=your-kimi-token
ANTHROPIC_BASE_URL=https://api.kimi.com/coding/
# ⚠️ Both are required. With the key but no endpoint, requests go to Anthropic
#    itself and fail with "401 invalid x-api-key". The endpoint can also be set
#    as `backend_url` in the config (see below).
# ⚠️ Do not use ANTHROPIC_AUTH_TOKEN — that is the Claude Code CLI convention.
#    This project runs on langchain, which only reads ANTHROPIC_API_KEY.

# ── Option H: Any OpenAI-compatible gateway (9Router / AI Router / self-hosted proxy) ──
OPENAI_COMPATIBLE_API_KEY=sk-xxx     # Also accepts OPENAI_API_KEY
BACKEND_URL=https://your-relay.example/v1   # Your gateway URL (can also be set in the Web sidebar "API Base URL")
```

### 3. 分析の実行

Python ファイル（例：プロジェクトのルートに `run.py`）を作成して下のスニペットを貼り付け、プロバイダーに合わせて `config` を調整してから、`uv run python run.py` を実行します。プロジェクトのルートに同梱されている `main.py` はこの例の実行可能なコピーなので、`uv run python main.py` でも動きます。

> `config` はリポジトリ内のファイルではありません。`TradingAgentsGraph(config=...)` に渡すただの dict です。上書きしたいキーだけを書けば、それ以外は `tradingagents/default_config.py` のデフォルト値が使われます（すべてのオプションは下の設定のセクションにあります）。

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph

# ── MiniMax Example (Recommended) ──────────────────────────────────────────
config = {
    "llm_provider": "minimax",
    "deep_think_llm": "MiniMax-M2.7",
    "quick_think_llm": "MiniMax-M2.7-highspeed",
    "output_language": "Chinese",
}

# ── DeepSeek Example ───────────────────────────────────────────────────────
# config = {
#     "llm_provider": "deepseek",
#     "deep_think_llm": "deepseek-chat",
#     "quick_think_llm": "deepseek-chat",
#     "output_language": "Chinese",
# }

# ── Anthropic + Kimi Example ───────────────────────────────────────────────
# config = {
#     "llm_provider": "anthropic",
#     "deep_think_llm": "claude-sonnet-4-6",
#     "quick_think_llm": "claude-sonnet-4-6",
#     "backend_url": "https://api.kimi.com/coding/",
#     "output_language": "Chinese",
# }

ta = TradingAgentsGraph(debug=True, config=config)
final_state, decision = ta.propagate("688017", "2026-05-12")
print(decision)
```

### 4. CLI モード

```bash
tradingagents                 # Interactive CLI
tradingagents analyze         # Same as above (default command)
tradingagents performance     # Decision performance report (see below)
tradingagents --help          # Show all options
```

### 5. 意思決定の成績レポート（v0.5.2 で追加）

**パイプラインの過去の判断が実際にどれだけ当たったか**を知るには：

```bash
tradingagents performance            # Human-readable report
tradingagents performance --json     # Machine-readable JSON
```

データはメモリログから取得されます。分析のたびに意思決定が記録され、同じ銘柄を次に分析したときに実際の株価を取得してリターンとアルファ（CSI 300 比）を埋めることで、その記録が確定します。**レポート自体は LLM 呼び出しを一切行いません**。ディスク上にすでにある結果を読むだけです。

主要な指標は **`direction_accuracy`** です。これは**判断が正しかったかどうかを測る唯一の指標**で、強気の格付けはアウトパフォームし、弱気の格付けはアンダーパフォームしていなければなりません。Hold はポジションを取らないため除外されます。あわせて `up_rate`（その銘柄が上昇した頻度）と `outperform_rate`（CSI 300 を上回った頻度）も報告します。**この 2 つは銘柄を表すものであり、意思決定を表すものではありません**。Sell の後に下落した場合は*正しい*判断ですが、`up_rate` には数えられません。

さらに、格付け別・銘柄別の内訳と、**格付けの識別力チェック**も含まれます。Buy から Sell までの 5 段階で、平均アルファは本当に単調に減少しているでしょうか。単調でない結果は、格付けに実質的な識別力がないことを意味します。

重要な注意事項：

- **これはバックテストではなく、戦略の成績でもありません。** 各記録は「ある日に下した 1 つの判断が、固定の保有期間の後にどう見えたか」です。期間は重なり合い、ポジションサイズもなく、取引コストやマーケットインパクトのコストも含まず、サンプルには選択バイアスがある可能性があります。
- **A 株はベータが強いです**。指数と一緒に上昇したことは正しかったことと同じではないため、方向の正確さはアルファで判定しています。生のリターンで判定すると実力を過大評価してしまいます。
- **有意性は指標ごとに数えます**。方向の正確さは方向性のある格付けだけを使うため、確定済みの総数は十分でも方向性のある件数が 20 件未満の場合、レポートはその指標を個別に警告します。
- **確定済みの記録が 20 件未満の場合、レポート自身がその旨を表示します**（「これらの比率はほぼノイズです」）。数件の記録から結論を出さないでください。
- リターンを解析できない記録は **0% として数えずにスキップします**。数えてしまうと、すべての統計が気付かないうちに中立へと引き寄せられてしまいます。

---
## Web UI

Streamlit による可視化インターフェースを内蔵しており、サイドバーで LLM プロバイダーとモデルを選択できます。銘柄コードを入力するとワンクリックで分析でき、コードを書きたくないユーザーに最適です。

### 起動

```bash
# Option 1: Start via command line (recommended)
tradingagents-web

# Option 2: Run directly
streamlit run web/app.py
```

ブラウザーを開いて `http://localhost:8501` にアクセスします。

### 機能

- **設定を記憶**：サイドバーで選んだプロバイダー / モデル / Base URL / サブスクリプションの適用範囲は `~/.tradingagents/llm_config.json` に書き込まれ、タブを開き直したり再起動したりしても復元されます（v0.5.17）
- **モデルの選択**：サイドバーで 10 の LLM プロバイダー（MiniMax/DeepSeek/Qwen/GLM/OpenAI/Anthropic/Google/xAI/OpenRouter/Ollama）を切り替えられるほか、任意の OpenAI 互換ゲートウェイ（9Router / AI Router / 自前のプロキシ）に接続するための **「OpenAI 兼容（自定义 base_url·9Router/AI Router/自建代理）」** にも対応しています
- **ワンクリック分析**：6 桁の A 株銘柄コード + 分析日 + 「数据起始日期」（デフォルトは当月の初日。テクニカル分析の振り返り期間をカスタマイズでき、月次/任意期間の分析に対応）を入力し、「开始分析」をクリックします
- **リアルタイムの進捗**：12 段階のパイプライン（7 人のアナリスト → 品質ゲート → ディベート → リスク管理 → 意思決定）をリアルタイムに表示し、完了したすべての段階のレポートを展開できます
- **完全なレポート**：シグナルカード（买入/持有/卖出）、7 人のアナリストのレポート、強気/弱気のディベート、リスク管理の評価
- **レポートのエクスポート**：**Markdown**（依存関係ゼロで常に利用可能）または **PDF** の完全な分析レポートをワンクリックでダウンロードできます（PDF は Windows/macOS/Linux の中国語フォントに自動で対応します）
- **履歴**：過去のすべての分析を自動的に保存して表示します

### スクリーンショット

<p align="center">
  <img src="assets/web-ui-welcome.png" width="80%" alt="Web UI のウェルカムページ"/>
</p>

---
## 設定

すべての設定は `config` 辞書を通じて渡します。すべてのオプション：

| パラメーター | デフォルト値 | 説明 |
|------|--------|------|
| `llm_provider` | `"openai"` | LLM プロバイダー：`minimax` / `deepseek` / `qwen` / `glm` / `openai` / `anthropic` / `google` / `xai` / `ollama` |
| `deep_think_llm` | `"gpt-5.4"` | リサーチマネージャー + ポートフォリオマネージャーが使うモデル |
| `quick_think_llm` | `"gpt-5.4-mini"` | すべてのアナリスト / リサーチャー / トレーダーが使うモデル |
| `backend_url` | `None` | カスタムの API エンドポイント / サードパーティの中継ゲートウェイ。Web UI のサイドバー、または `.env` ファイルの `BACKEND_URL` で指定できます。中国国内からプロキシ経由で Claude / OpenAI にアクセスする場合に便利です。**リモートの Ollama に接続する方法でもあります**：`llm_provider` を `ollama` に、`backend_url` を `http://<host>:11434/v1` に設定します。未設定の場合はローカルの `http://localhost:11434/v1` がデフォルトになります（#61） |
| `role_llms` | `{}` | **オプション**：個々のロールに別のモデルを割り当てます（例：強気と弱気で異なるベンダーのモデルを使う）。空の場合は、これまでどおりすべてのロールが quick/deep のペアを使います。下の「ロールごとのモデル」をご覧ください。#39 |
| `max_tokens` | `None` | 1 回の応答あたりの最大出力トークン数。`None` = プロバイダー自身のデフォルト。**レポートが文の途中で止まる場合は、まずこれを増やしてください**（これは出力の上限であり、コンテキストウィンドウではありません）。`TRADINGAGENTS_MAX_TOKENS` でも設定できます。#91 |
| `output_language` | `"Chinese"` | レポート出力の言語（内部のディベートは常に英語） |
| `market_lookback_days` | `None` | テクニカル分析の振り返り期間（日数）（分析範囲 = 開始日 → 分析日）。Web/CLI では「数据起始日期」から自動的に計算されます。`None` = モデルが選択（約 30 日）。#16 |
| `llm_timeout` | `150` | LLM リクエストごとのタイムアウト（秒）。**LangChain のクライアントを経由するすべてのプロバイダーに適用されます**（`openai` / `anthropic` / `google` / `azure` と、すべての OpenAI 互換のもの。クォータのフォールバック用クライアントにも引き継がれます）。以前はタイムアウトがまったくありませんでした。3 つの LangChain ラッパー（ChatOpenAI / ChatAnthropic / AzureChatOpenAI）はいずれも、タイムアウトが指定されていない場合に下層の SDK へ `None` を**明示的に**渡し、httpx にとってそれは「タイムアウトなし」を意味します。そのため、ゲートウェイがハングすると分析が**永遠に**止まってしまいました（プロセスは生きているが、出力がなく、戻ってこない）。`claude_agent_sdk` のサブスクリプション上書きの**メインの経路**は LangChain のクライアントを経由しません。v0.5.20 以降、このクライアントは同じ設定を独自に実装しています。1 回のサブスクリプション呼び出しの予算は、この値 × その呼び出しで実行されうるモデルのターン数です（Agent SDK は**1 回の**呼び出しの中でツールループ全体を実行します。シングルターンの呼び出しではちょうどこの値になります）。タイムアウトした場合は、レート制限と同じ経路でフォールバックします。推論モデルが最初のトークンまでに日常的にこれより長い時間を必要とする場合は、値を増やしてください（#100） |
| `llm_max_retries` | `3` | アプリケーションレベルのリトライ回数。408 / 409 / 429 / 5xx と接続エラー（読み取りタイムアウトを含む）を対象とし、これはまさに OpenAI SDK がかつてリトライしていたものと同じです。**OpenAI 互換のクライアントを経由するプロバイダーにのみ適用されます**（`openai` / `deepseek` / `qwen` / `glm` / `minimax` / `xai` / `openrouter` / `ollama` / `openai_compatible`）。これらの SDK レベルのリトライだけがゼロにされ、アプリケーション層に引き渡されます。Anthropic / Google / Azure は、それぞれの SDK のリトライをそのまま保持します |
| `llm_retry_delay` | `5` | リトライの初期バックオフ（秒）。毎回 2 倍になります：5s → 10s → 20s |
| `max_debate_rounds` | `1` | 強気 vs 弱気のディベートのラウンド数 |
| `max_risk_discuss_rounds` | `1` | 三者によるリスクディベートのラウンド数 |
| `data_vendors` | すべて `"a_stock"` | データベンダーのルーティング |
| `checkpoint_enabled` | `False` | SQLite によるチェックポイント/再開を有効にする |
| `memory_log_max_entries` | `None` | トレーディングメモリの最大エントリ数 |

### ロールごとのモデル（オプション、v0.5.0 で追加）

デフォルトでは、すべてのロールが `quick_think_llm` / `deep_think_llm` のペアを共有します。**ほとんどの人は単一のベンダーで実行するため、この機能は必要ありません**。

複数のモデルを利用できる場合は、特定のロールにモデルを割り当てられます。主な用途は、**強気と弱気のリサーチャーに異なるベンダーのモデルを使わせること**です。1 つのモデルが両方の立場を演じると自分自身に同意しがちで、本当の反論は基盤となるモデルが異なって初めて現れます。

```python
config = {
    "llm_provider": "deepseek",          # roles you do not list still use this
    "deep_think_llm": "deepseek-chat",
    "quick_think_llm": "deepseek-chat",
    "role_llms": {
        "bull": {"provider": "qwen", "model": "qwen-plus"},
        "bear": {"provider": "glm",  "model": "glm-4.6"},
        # omit provider to keep llm_provider and only swap the model:
        "portfolio_manager": {"model": "deepseek-reasoner"},
    },
}
```

有効なロール名（指定しなかったものは quick/deep のデフォルトのままです）：

| グループ | ロール |
|-------|-------|
| 7 人のアナリスト | `market` `social` `news` `fundamentals` `policy` `hot_money` `lockup` |
| ディベートと意思決定 | `bull` `bear` `research_manager` `trader` |
| リスクの 3 者 | `risk_aggressive` `risk_neutral` `risk_conservative` |
| その他 | `quality_gate` `portfolio_manager` |

注意事項：

- **ロール名のスペルを間違えると、無視されずにすぐにエラーになります**。そうしないと、設定が反映されていないのに反映されたと思い込んでしまうためです。
- **プロバイダーとモデルが同じものは 1 つのインスタンスを共有する**ため、7 つのロールを列挙しても 7 つの接続が開かれるわけではありません。
- 各プロバイダーは**それぞれ独自の** API キーの変数（`DEEPSEEK_API_KEY` / `DASHSCOPE_API_KEY` / `ZHIPU_API_KEY` …）を使います。不足している場合は変数名を示して報告されます。
- `backend_url` はベンダーをまたいで引き継がれ**ません**（メインのプロバイダーに属するものです）。必要な場合は、ロールのエントリ内で `backend_url` を設定してください。
- `claude_agent_sdk` のサブスクリプション上書きを有効にしている場合、`role_llms` に列挙したロールは**サブスクリプションを経由せず、トークン単位で課金されます**。影響を受けるロールは、起動時の警告で名前が示されます。

---

## よくあるトラブルシューティング

**Q：DeepSeek/通義/智譜を使っているのに `OpenAIError: The api_key client option must be set ... OPENAI_API_KEY` が出る？**
各プロバイダーは `OPENAI_API_KEY` ではなく、**それぞれ独自の環境変数**を使います：DeepSeek=`DEEPSEEK_API_KEY`、通義=`DASHSCOPE_API_KEY`、智譜=`ZHIPU_API_KEY`、MiniMax=`MINIMAX_API_KEY`、xAI=`XAI_API_KEY`、OpenRouter=`OPENROUTER_API_KEY`、OpenAI 互換（カスタム）=`OPENAI_COMPATIBLE_API_KEY`。プロジェクトのルートにある `.env` ファイルで対応する変数を設定し、プログラムを**再起動**してください。（v0.2.12 以降、キーが不足している場合は、どの変数名を使うべきかが直接表示されます。）

**Q：カスタムの base_url + モデルで、OpenAI 互換のサードパーティゲートウェイ/中継（9Router、AI Router、自前のプロキシ）に接続したい？**
**「OpenAI 兼容（自定义 base_url·9Router/AI Router/自建代理）」** オプション（v0.2.20 で追加）を使ってください。Web のサイドバーで「LLM 供应商」からそれを選択 → 「快速思考模型 ID」/「深度思考模型 ID」にゲートウェイが対応しているモデル名を手動で入力 → 「API Base URL」にゲートウェイのアドレス（例：`https://your-relay.example/v1`）を入力 → `.env` で `OPENAI_COMPATIBLE_API_KEY=your_key` を設定します（`OPENAI_API_KEY` も受け付けます）。CLI では、`OpenAI-Compatible` を選択すると Base URL の入力を求められます。互換性を最大限にするため、（OpenAI Responses API ではなく）標準の Chat Completions を使い、モデル名は組み込みのリストに縛られず自由に入力できます。同等の設定は次のとおりです：`llm_provider="openai_compatible"` + `backend_url="<your_gateway>"` + `deep_think_llm/quick_think_llm="<your_model>"`。

**Q：Python 3.12/3.14 をインストールしているのに、`pip install -e .` で `requires a different Python: 3.9.6 not in '>=3.10'` と表示される？**
**このメッセージの 3.9.6 は、現在の `pip` が紐付いているインタープリターです**。新しくインストールしたバージョンは使われていません（macOS では、付属の `pip3` がシステムの 3.9 を指していることがよくあります）。どのインタープリターが使われているかを確認してください：

```bash
pip3 -V                    # the path in parentheses is its Python
python3.12 -m pip -V       # same check for the version you want
```

`python -m pip` を使えば取り違えを避けられます。仮想環境の利用をおすすめします：

```bash
python3.12 -m venv .venv && source .venv/bin/activate
python -m pip install -e .
```

Windows では `py -3.12 -m venv .venv` + `.venv\Scripts\activate` を使ってください。（#92）

**Q：コンテキストウィンドウはまったく埋まっていないのに、レポートが途中で止まる？**
コンテキストの上限ではなく、**出力**の上限に達しています。モデルが 1 回の応答で出力できるトークン数は、別の制限です。v0.4.1 以降、この切り捨てはレポートの半分を黙って渡すのではなく、ログで報告されます（`因为达到输出上限被截断` / 出力上限で切り捨て）。設定の `max_tokens`（例：`"max_tokens": 16000`）または環境変数 `TRADINGAGENTS_MAX_TOKENS` で上限を引き上げてください。

また、**サードパーティのモデル名（Kimi など）を `anthropic` プロバイダー経由で実行する**場合、langchain はそのモデルを認識できず、非常に小さいデフォルトの出力上限を適用するため、レポートが一様に短くなります。v0.4.1 以降、これらのモデルのデフォルトは 8192 です。それ以上必要な場合は `max_tokens` を明示的に設定してください。#91

**Q：Kimi で `401 invalid x-api-key` が出る？**
リクエストが Kimi ではなく **Anthropic 自体**に届いています。キーは指定したものの、エンドポイントを指定していません。両方が必要です：

```bash
ANTHROPIC_API_KEY=your-kimi-token
ANTHROPIC_BASE_URL=https://api.kimi.com/coding/   # or set backend_url in the config
```

なお、**ここでは `ANTHROPIC_AUTH_TOKEN` は効果がありません**。これは Claude Code CLI の慣習です。本プロジェクトは langchain 上で動作し、langchain が読むのは `ANTHROPIC_API_KEY` だけです。v0.4.1 以降、エンドポイントなしで Claude 以外のモデル名を使うと、Anthropic からのわかりにくい 401 ではなく、説明付きで**起動時に**失敗します。#89

**Q：PDF をエクスポートすると `UnicodeEncodeError: 'latin-1' codec can't encode` が出る？**
環境に**古いバージョンの `fpdf`（pyfpdf）** がインストールされており、本プロジェクトが使う `fpdf2` と競合しています。どちらも `fpdf` という名前でインポートされるためです。`pip uninstall -y fpdf && pip install "fpdf2>=2.8.6"` を実行してください。それでも解決しない場合は、代わりに「下载 Markdown」によるエクスポートを使えます（依存関係ゼロで常に利用可能）。

**Q：Docker で PDF をエクスポートすると「中国語フォントが見つからない」と表示される？**
v0.2.12 以降、Dockerfile には `fonts-noto-cjk` が組み込まれています。`docker build` で再ビルドするだけで解決します。古いイメージの場合は、一時的に `apt install fonts-noto-cjk` を実行するか、Markdown でのエクスポートに切り替えてください。

**Q：Docker の起動が `[Errno 13] Permission denied: /home/appuser/.tradingagents/cache` で失敗する？**
古いイメージでは、データディレクトリが事前に作成されていませんでした。`docker-compose` の名前付きボリュームをマウントすると、Docker はそれを `root` 所有で作成しますが、コンテナ内のプロセスは `appuser` として実行されるため書き込めません。v0.2.14 以降、Dockerfile は `/home/appuser/.tradingagents`（cache/logs/memory）を事前に作成して所有者を `appuser` に設定するため、名前付きボリュームはこの所有権を引き継ぎます。**アップグレード方法**：`git pull` の後、`docker compose build --no-cache` でイメージを再ビルドします。古いデータボリュームを残したい場合は、先に `docker run --rm -v tradingagents_data:/d alpine chown -R 1000:1000 /d` を実行して所有権を修正してください。そうでなければ、`docker volume rm tradingagents_data` でボリュームを削除してから再ビルドするだけです。

**Q：一部のアナリストのレポート（センチメント/ニュース/ファンダメンタルズ/政策/仕手筋/ロックアップ解除）が空で表示されない？**
これらのレポートは、対応するアナリストがデータツールを呼び出した後に生成されます。**空のレポートは自動的にスキップされ、表示されません。** データソース自体は正常です（騰訊/mootdx/同花順/東方財富はテスト済みで、データを返します）。レポートが空になるのは、通常は**選択したモデルのツール呼び出し能力が弱い**ためです（例：deepseek/minimax の一部の軽量モデルは、ツールを呼び出す際に不安定です）。ツール呼び出しがより安定したモデル（deepseek-chat / 通義 / GLM-4 / Claude / GPT など）に切り替えるか、再試行することをおすすめします。

**Q：なぜ `[google]` extra がなくなったのですか？ Gemini はどうやってインストールしますか？**
**`[google]` extra は v0.3.1 で削除されました**（[#87](https://github.com/simonlin1212/TradingAgents-astock/issues/87)）。`langchain-google-genai>=4.0.0` は `google-genai>=1.53.0` を必要とし、その範囲の google-genai のリリースは**すべて** `httpx>=0.28.1` を必要とします。一方、mootdx（A 株データの中核となるソース）は `httpx>=0.25,<0.26` に固定しています。**両方を満たすバージョンの組み合わせは存在せず、この競合はバージョン指定の誤りではなく構造的なものです。**

実際の問題は、**uv がすべての extra を対象とするユニバーサルなロックを作成する**ことです。そのため、extra を宣言しただけで、Gemini をまったく使わないユーザーも含めて**全員**の `uv sync` が失敗していました。空のままにするのはさらに悪い選択です（`pip install .[google]` が何もインストールせずに黙って終わってしまいます）。そこで extra は削除され、`google_client.py` は正確なインストールコマンドを含む ImportError を送出するようになりました。

Gemini を使うには、明示的にインストールしてください（**mootdx は TCP 上で TDX プロトコルを話し、実行時に httpx をインポートすることはない**ため、実際には httpx を上げても安全です）：

```bash
pip install --no-deps "langchain-google-genai>=4.0.0"
pip install "google-genai>=1.53.0" "httpx>=0.28.1"
```

または、Gemini を別の仮想環境で使ってください。最も簡単なのは、DeepSeek / MiniMax / Qwen / 任意の OpenAI 互換ゲートウェイを使うことで、競合を完全に回避できます。

補足：**litellm / mcp は本プロジェクトの依存関係ではありません**。エラーにそれらが出てくる場合は、環境内の別のパッケージに由来するものです。

**Q：CLI の対話モードに入らずに複数の銘柄をバッチ実行し、CLI と同じ完全なレポートを得るには？**
`examples/run_cases.py` をご覧ください。CLI の `save_report_to_disk()` 関数を再利用し、銘柄ごとに CLI と同じ `complete_report.md`（Analyst / Research / Trading / Risk / Portfolio の 5 セクション）と、完全な `summary.json` を出力します。使い方：`uv run python examples/run_cases.py`（すべて実行）または `uv run python examples/run_cases.py 688017`（単一銘柄）。プロバイダー/モデルを切り替えるには `build_config()` を変更してください。
## プロジェクト構成

```
TradingAgents-Astock/
├── tradingagents/
│   ├── agents/
│   │   ├── analysts/          # 7 analysts
│   │   │   ├── market_analyst.py
│   │   │   ├── social_media_analyst.py
│   │   │   ├── news_analyst.py
│   │   │   ├── fundamentals_analyst.py
│   │   │   ├── policy_analyst.py        # A-share specialized
│   │   │   ├── hot_money_tracker.py     # A-share specialized
│   │   │   └── lockup_watcher.py        # A-share specialized
│   │   ├── researchers/       # Bull / Bear researchers
│   │   ├── risk_mgmt/         # Aggressive / Conservative / Neutral debaters
│   │   ├── managers/          # Research Manager + Portfolio Manager
│   │   ├── trader/            # Trader (A-share trading constraints)
│   │   └── utils/             # State definitions, utility functions
│   ├── dataflows/
│   │   ├── a_stock.py         # A-share data vendor (direct HTTP API, zero third-party libraries)
│   │   ├── interface.py       # Data interface abstraction layer
│   │   └── ...
│   └── graph/
│       ├── trading_graph.py   # Main entry point: TradingAgentsGraph
│       ├── setup.py           # LangGraph topology definition
│       ├── propagation.py     # State initialization and propagation
│       ├── reflection.py      # Trading reflection (CSI 300 benchmark)
│       └── conditional_logic.py
├── web/
│   ├── app.py                 # Streamlit main entry
│   ├── runner.py              # Backend thread running analysis
│   ├── progress.py            # Thread-safe progress tracking
│   ├── history.py             # History record scanning
│   ├── pdf_export.py          # PDF report generation
│   ├── launch.py              # CLI launcher
│   └── components/            # UI components
│       ├── sidebar.py         # Sidebar (inputs + history)
│       ├── progress_panel.py  # Real-time progress panel
│       └── report_viewer.py   # Report display
├── test_astock.py             # E2E integration tests
├── CHANGES_FROM_UPSTREAM.md   # Complete change log versus upstream
├── NOTICE                     # Apache 2.0 attribution notice
├── LICENSE                    # Apache 2.0 license
└── pyproject.toml             # Package definition and dependencies
```
## 謝辞

本プロジェクトは [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) オープンソースプロジェクトをベースに、中国の A 株市場向けに適応させたものです。オリジナルの作者の皆さまの素晴らしい仕事と、Apache 2.0 のオープンソース精神に感謝します。

**原論文**：[TradingAgents: Multi-Agents LLM Financial Trading Framework](https://arxiv.org/abs/2412.20138)

---
## プロジェクトの位置付け

**これはフレームワークのエンジニアリング実装であり、投資商品ではありません。**

- **これは何か**：[TradingAgents 論文](https://arxiv.org/abs/2412.20138)（TauricResearch）のマルチエージェントアーキテクチャを A 株向けにエンジニアリング実装したもので、研究と教育のために設計されています。具体的には、金融テキストにおけるマルチエージェントのディベートの挙動、A 株のデータソースの統合方法、構造化された出力の実現方法を研究するためのものです。
- **これは何ではないか**：投資顧問でも、銘柄推奨サービスでもなく、いかなる投資サービスも提供しません。このリポジトリは、特定の有価証券に関する分析レポート、格付け、売買の推奨を公開しません。`examples/` ディレクトリには自分で実行できるスクリプトだけが含まれており、個別銘柄についての事前に生成された結論はありません。
- **モデルとデータはあなたのもの**：LLM の API キーは自分で設定し、自分のマシンで実行します。出力された内容はあなたのものであり、あなた自身が判断し、あなた自身が責任を負います。プロジェクト自体はサービスをホストせず、あなたに代わって分析を行うこともなく、あなたの実行結果にアクセスすることもありません。
- **実行可能な価格水準は生成しません**：このフレームワークは、エントリー価格、損切りの水準、ポジションサイズ、目標価格といったポジションを出力**しません**。これはデフォルトでオフになっている機能ではなく、コードにそもそも存在しないものです。トレーダーとポートフォリオマネージャーは、方向、格付け、根拠だけを示します。この機能が必要なユーザーは、コードをフォークして自分で追加できます（Apache-2.0 で許可されています）が、関連するすべての責任を負い、自身の法域における資格要件を自ら確認する必要があります。

> **⚠️ 免責事項**
>
> - 本システムが生成するすべての内容は AI によって自動的に作成されたものであり、誤りや偏りを含む可能性があります。
> - 本プロジェクトはいかなる投資助言にも当たりません。投資の判断については、中国証券監督管理委員会が発行した資格を持つ専門機関にご相談ください。
> - 本ツールの使用によって生じたいかなる投資損失についても、作者は一切の責任を負いません。
> - 株式市場にはリスクがあります。投資は慎重に行ってください。

---

## ライセンス

[Apache License 2.0](./LICENSE)

本プロジェクトは TauricResearch/TradingAgents のフォークであり、Apache 2.0 ライセンスを継承しています。[NOTICE](./NOTICE) をご覧ください。

**作者：** Simon Lin · X [@linsizhen](https://x.com/linsizhen) · Email: [simonlin0423@gmail.com](mailto:simonlin0423@gmail.com)
