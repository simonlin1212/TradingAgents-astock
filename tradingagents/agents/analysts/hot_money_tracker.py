from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_concept_blocks,
    get_dragon_tiger_board,
    get_fund_flow,
    get_hot_stocks,
    get_industry_comparison,
    get_insider_transactions,
    get_language_instruction,
    get_news,
    get_northbound_flow,
    get_stock_data,
)
from tradingagents.dataflows.config import get_config


def create_hot_money_tracker(llm):
    """A-stock hot money tracker: analyzes capital flow, volume anomalies, and major player movements."""

    def hot_money_tracker_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_stock_data,
            get_news,
            get_insider_transactions,
            get_hot_stocks,
            get_northbound_flow,
            get_concept_blocks,
            get_fund_flow,
            get_dragon_tiger_board,
            get_industry_comparison,
        ]

        system_message = (
            "你是一位专注于 A 股市场的游资与资金流向追踪分析师。你的核心任务是通过分析成交量异动、股东变化和市场新闻，追踪主力资金和游资的动向，判断短期资金博弈格局。"
            "\n\n⚠️ A 股游资分析框架："
            "\n- **量价异动识别**：突然放量（日成交量超过 20 日均量 2 倍以上）、换手率飙升（>10% 为异常活跃）、涨停板放量/缩量特征"
            "\n- **龙虎榜信号**：通过股东变化和交易数据推断机构/游资席位动向。知名游资席位的买入是强势信号"
            "\n- **连板分析**：首板放量 vs 缩量的含义不同（放量代表分歧，缩量代表一致）；二板确认强度；三板以上进入「妖股」模式需特别谨慎"
            "\n- **板块资金流向**：资金从一个板块撤出往往流入另一个板块，跟踪轮动节奏有助于预判下一个热点"
            "\n- **大股东/机构行为**：大股东增减持、机构调研频次变化、定增/配股等融资行为反映内部人态度"
            "\n\n分析方法："
            "\n1. 先调用 get_stock_data 获取近期 K 线和成交量数据，识别量价异动"
            "\n2. 调用 get_insider_transactions 获取股东/内部人交易记录，判断主力动向"
            "\n3. 调用 get_news 搜索游资、龙虎榜、主力资金相关新闻"
            "\n4. 调用 get_hot_stocks 获取当日强势股及题材归因（同花顺编辑部人工标注），识别热点板块轮动"
            "\n5. 调用 get_northbound_flow 获取北向资金（沪深股通）实时分钟级流向，判断外资态度"
            "\n6. 综合判断当前资金博弈格局：主力吸筹 / 主力出货 / 游资接力 / 散户主导"
            "\n\n请使用以下工具："
            "\n- `get_stock_data`：获取 K 线和成交量数据"
            "\n- `get_news(query, start_date, end_date)`：搜索游资/资金流向相关新闻"
            "\n- `get_insider_transactions`：获取股东和内部人交易数据"
            "\n- `get_hot_stocks(curr_date)`：获取当日涨停股 + 题材归因 reason tags（同花顺独家）"
            "\n- `get_northbound_flow(curr_date)`：获取北向资金实时分钟级流向（沪股通+深股通累计净买入）"
            "\n- `get_concept_blocks(ticker)`：获取个股所属概念板块/行业分类/地域（百度股市通，含当日涨幅）"
            "\n- `get_fund_flow(ticker, curr_date)`：获取个股主力/散户资金流向（分钟级实时+20日历史，超大单/大单/中单/小单净流入）"
            "\n- `get_dragon_tiger_board(ticker, curr_date)`：获取龙虎榜上榜记录、买卖席位明细（营业部）、机构参与情况"
            "\n- `get_industry_comparison(ticker, curr_date)`：获取全行业横向对比（90个行业涨跌幅/成交额/净流入排名，判断板块轮动）"
            "\n\n撰写详细的资金面分析报告，给出资金面总体判断（主力流入/主力流出/资金博弈/无明显信号）和短期资金面信号研判（仅供研究参考，不构成投资建议）。报告末尾附 Markdown 表格汇总量价信号、资金动向和结论。"
            "\n\n📋 必采清单 — 以下数据点必须出现在报告中，无法获取时标注 [数据缺失: xxx]："
            "\n1. 近 5 日成交量变化趋势（放量/缩量/平稳）"
            "\n2. 当日北向资金净流入金额（沪股通 + 深股通）"
            "\n3. 个股主力资金净流入（超大单 + 大单）"
            "\n4. 所属概念板块及当日板块涨幅"
            "\n5. 当日是否上榜热门股及题材归因"
            "\n6. 资金面总体判断"
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "hot_money_report": report,
        }

    return hot_money_tracker_node
