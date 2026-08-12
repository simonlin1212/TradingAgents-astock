from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_fund_flow,
    get_hot_stocks,
    get_language_instruction,
    get_news,
    get_stock_data,
)
from tradingagents.dataflows.config import get_config


def create_social_media_analyst(llm):
    def social_media_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        # 情绪不能只靠读新闻推断（#61）：光看文本，模型很容易把"这条新闻听起来利好"
        # 当成"市场情绪乐观"，而资金可能正在流出。加上资金流 / 热度榜 / 量价三样
        # 可核对的硬数据，让情绪判断有据可依，也能暴露"消息面与资金面背离"。
        tools = [
            get_news,
            get_fund_flow,
            get_hot_stocks,
            get_stock_data,
        ]

        system_message = (
            "你是一位专注于 A 股市场的市场情绪分析师。你的任务是通过分析公司相关新闻、市场讨论和公众情绪，判断市场对目标公司的整体态度和情绪走向。"
            "\n\n⚠️ A 股情绪分析框架："
            "\n- **散户情绪权重高**：A 股散户占比超过 60%，市场情绪对股价的短期影响远大于成熟市场。恐慌和贪婪的情绪波动更剧烈。"
            "\n- **舆论阵地**：东方财富股吧、雪球、同花顺社区是 A 股投资者最活跃的讨论平台。分析新闻时注意推断这些平台可能的情绪反应。"
            "\n- **情绪指标**：关注以下情绪信号 - 连续涨停后的追涨情绪、业绩暴雷后的恐慌抛售、机构调研后的预期变化、热门概念炒作的跟风程度。"
            "\n- **反向指标**：当市场情绪一致性过高（极度乐观或极度悲观）时，往往是反转信号。散户一致看多可能是阶段顶部。"
            "\n- **时间维度**：区分短期情绪波动（1-3 天，由单一事件驱动）和中期情绪趋势（1-4 周，由基本面变化驱动）。"
            "\n\n🔧 工具与取数顺序（ticker 一律用 6 位代码）："
            "\n1. `get_fund_flow(ticker, curr_date)` — 主力/超大单/大单资金净流入（当日分钟级 + 近 20 日）。**这是情绪最硬的证据：嘴上说什么，不如钱往哪走。**"
            "\n2. `get_stock_data(ticker, start_date, end_date)` — 近期量价。用成交量的放大/萎缩、涨跌幅的连续性判断情绪强度。"
            "\n3. `get_hot_stocks(curr_date)` — 当日强势股与题材归因榜。看目标股是否在榜、所属题材是否正被资金追逐。"
            "\n4. `get_news(ticker, start_date, end_date)` — 新闻与市场讨论，用于解释情绪的**成因**。"
            "\n\n⚠️ 分析纪律 —— 情绪判断必须落在数据上，不能只凭新闻语气推断："
            "\n- **先看资金，再看新闻**。新闻只能解释情绪从哪来，不能单独作为情绪结论的依据。"
            "\n- **背离必须写出来**：消息面正面但主力资金持续净流出（或相反），是本报告最有价值的信号，务必单列指出并给出你的解读。"
            "\n- **区分「热度」与「情绪方向」**：上榜、放量只说明关注度高，方向要由资金流向和涨跌结构判断。恐慌抛售同样是高热度。"
            "\n- 数据取不到时如实标注，**不要用新闻语气去补一个编造的数字**。"
            "\n\n撰写详细的市场情绪分析报告，包含情绪评分（极度悲观/悲观/中性/乐观/极度乐观）和趋势判断。报告末尾附 Markdown 表格汇总情绪信号和结论。"
            "\n\n📋 必采清单 — 以下数据点必须出现在报告中，无法获取时标注 [数据缺失: xxx]："
            "\n1. 主力资金当日净流入金额、近 20 日累计净流入方向"
            "\n2. 近期成交量变化（放量/缩量，相对前期均量的倍数）"
            "\n3. 是否出现在当日强势股榜、所属题材标签"
            "\n4. 新闻检索条数和时间范围"
            "\n5. 正面/负面/中性新闻比例"
            "\n6. 排名前 3 的舆情主题"
            "\n7. **资金面与消息面是否背离**（一致/背离，背离时说明方向）"
            "\n8. 情绪评分（极度悲观/悲观/中性/乐观/极度乐观）"
            "\n9. 情绪趋势变化方向（升温/降温/平稳）"
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
            "sentiment_report": report,
        }

    return social_media_analyst_node
