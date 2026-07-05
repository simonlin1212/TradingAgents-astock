from tradingagents.agents.analysts.social_media_analyst import create_social_media_analyst
from tradingagents.graph.trading_graph import TradingAgentsGraph
from langchain_core.runnables import RunnableLambda


def test_social_tool_node_registers_kol_summary_tool():
    tool_nodes = TradingAgentsGraph.__new__(TradingAgentsGraph)._create_tool_nodes()

    names = {tool.name for tool in tool_nodes["social"].tools_by_name.values()}

    assert "get_kol_summary" in names


def test_social_prompt_mentions_required_kol_evidence():
    class CapturingLLM:
        def bind_tools(self, tools):
            self.tools = tools
            return RunnableLambda(self.invoke)

        def invoke(self, _messages):
            return type("Result", (), {"tool_calls": [], "content": "ok"})()

    llm = CapturingLLM()
    node = create_social_media_analyst(llm)

    result = node(
        {
            "trade_date": "2026-07-05",
            "company_of_interest": "300750",
            "messages": [],
        }
    )

    tool_names = {tool.name for tool in llm.tools}
    assert "get_kol_summary" in tool_names
    assert result["sentiment_report"] == "ok"
